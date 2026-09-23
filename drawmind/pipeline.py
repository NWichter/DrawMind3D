"""The analysis pipeline: PDF drawing plus STEP model to matched features.

This is the entry point for embedding DrawMind3D. The CLI and the web
application are thin wrappers around `analyze()`; nothing they do is
unavailable here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from drawmind.models import AnnotationType, HoleGroup, MatchResult, PDFAnnotation

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int], None]


class StageStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class Stage:
    """What one pipeline step actually did."""

    name: str
    status: StageStatus
    detail: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True)
class Settings:
    """Caller-controlled pipeline behaviour.

    `use_llm=False` is a hard guarantee: no part of the run contacts an
    external model provider.
    """

    use_llm: bool = True
    unit_system: Optional[str] = None
    vision_dpi: Optional[int] = None


@dataclass
class AnalysisResult:
    raw_texts: list[dict] = field(default_factory=list)
    annotations: list[PDFAnnotation] = field(default_factory=list)
    holes: list[HoleGroup] = field(default_factory=list)
    matches: list[MatchResult] = field(default_factory=list)
    unmatched_annotations: list[PDFAnnotation] = field(default_factory=list)
    unmatched_holes: list[HoleGroup] = field(default_factory=list)
    unit_system: str = "metric"
    unit_source: str = ""
    stages: list[Stage] = field(default_factory=list)
    shape: object = None

    @property
    def llm_used(self) -> bool:
        """True only if a model contributed to this result."""
        return any(
            s.status in (StageStatus.OK, StageStatus.PARTIAL)
            and s.name in ("vision_llm", "llm_disambiguation")
            for s in self.stages
        )

    @property
    def warnings(self) -> list[str]:
        return [
            f"{s.name}: {s.detail}"
            for s in self.stages
            if s.status in (StageStatus.FAILED, StageStatus.PARTIAL) and s.detail
        ]

    @property
    def other_annotations(self) -> list[PDFAnnotation]:
        """Everything read from the drawing that matching does not cover."""
        accounted = {m.annotation_id for m in self.matches}
        accounted |= {a.id for a in self.unmatched_annotations}
        return [a for a in self.annotations if a.id not in accounted]

    def stage(self, name: str) -> Optional[Stage]:
        return next((s for s in self.stages if s.name == name), None)


def analyze(
    pdf_path: str | Path,
    step_path: str | Path,
    settings: Settings | None = None,
    progress: ProgressFn | None = None,
) -> AnalysisResult:
    """Run the full pipeline and report what each step achieved.

    Args:
        pdf_path: Technical drawing PDF.
        step_path: STEP/STP solid model of the same part.
        settings: Behaviour switches; defaults enable the LLM when a key is set.
        progress: Called with (message, percent) after each step.

    Returns:
        An AnalysisResult whose `stages` record the real outcome of every
        step, including the ones that were skipped or failed.
    """
    from drawmind.config import MAX_PDF_PAGES, USE_VISION_LLM
    from drawmind.pdf import backend

    settings = settings or Settings()
    pdf_path = Path(pdf_path)
    step_path = Path(step_path)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not step_path.is_file():
        raise FileNotFoundError(f"STEP model not found: {step_path}")

    with backend.open_document(pdf_path) as doc:
        page_count = len(doc)
    if page_count > MAX_PDF_PAGES:
        raise ValueError(
            f"PDF has {page_count} pages, limit is {MAX_PDF_PAGES} (set MAX_PDF_PAGES to raise it)"
        )

    llm_allowed = bool(settings.use_llm and USE_VISION_LLM)
    result = AnalysisResult()

    def report(message: str, percent: int) -> None:
        if progress:
            progress(message, percent)

    report("Extracting text from PDF", 10)
    _run_extraction(result, pdf_path, settings, llm_allowed)

    report("Analyzing drawing with vision model", 25)
    _run_vision(result, pdf_path, llm_allowed)

    if not settings.unit_system:
        _recheck_units(result, pdf_path, llm_allowed)

    report("Tracing leader lines", 45)
    _run_leader_lines(result, pdf_path)

    report("Extracting features from STEP", 60)
    _run_cad(result, step_path)

    report("Matching annotations to features", 80)
    _run_matching(result, pdf_path, llm_allowed)

    report("Complete", 100)
    return result


def _record(result: AnalysisResult, name: str, status: StageStatus, detail: str = "") -> None:
    result.stages.append(Stage(name=name, status=status, detail=detail))


def _run_extraction(
    result: AnalysisResult,
    pdf_path: Path,
    settings: Settings,
    llm_allowed: bool,
) -> None:
    from drawmind.pdf.extractor import _tesseract_available, detect_unit_system, extract_all_text
    from drawmind.pdf.parser import parse_annotations

    extraction: dict = {}
    raw_texts = extract_all_text(str(pdf_path), report=extraction)
    result.raw_texts = raw_texts
    native = sum(1 for t in raw_texts if t.get("source") == "native")
    ocr = sum(1 for t in raw_texts if str(t.get("source", "")).startswith("ocr"))

    _record(
        result,
        "text_extraction",
        StageStatus.OK if raw_texts else StageStatus.FAILED,
        f"{native} native, {ocr} OCR text elements"
        if raw_texts
        else "no text recovered from the PDF",
    )

    ocr_errors = extraction.get("ocr_errors", [])
    if ocr_errors:
        failed_all = len(ocr_errors) >= extraction.get("ocr_pages", 0)
        _record(
            result,
            "ocr",
            StageStatus.FAILED if failed_all else StageStatus.PARTIAL,
            f"{ocr} text elements from OCR; failed on {'; '.join(ocr_errors)}",
        )
    elif ocr:
        _record(result, "ocr", StageStatus.OK, f"{ocr} text elements from OCR")
    elif not _tesseract_available():
        _record(
            result,
            "ocr",
            StageStatus.SKIPPED,
            "Tesseract executable not found; scanned drawings cannot be read",
        )
    elif extraction.get("ocr_pages"):
        _record(result, "ocr", StageStatus.OK, "ran, but recovered no text beyond the native layer")
    else:
        _record(result, "ocr", StageStatus.SKIPPED, "native text layer was sufficient")

    if settings.unit_system:
        result.unit_system = settings.unit_system
        result.unit_source = "caller"
        _record(result, "unit_detection", StageStatus.OK, f"{result.unit_system} (caller-supplied)")
    else:
        units: dict = {}
        result.unit_system = detect_unit_system(str(pdf_path), use_llm=llm_allowed, report=units)
        result.unit_source = units.get("source", "")
        if units.get("error"):
            _record(
                result,
                "unit_detection",
                StageStatus.PARTIAL,
                f"{result.unit_system} (default; vision check failed: {units['error']})",
            )
        else:
            _record(result, "unit_detection", StageStatus.OK, result.unit_system)

    result.annotations = parse_annotations(raw_texts, unit_system=result.unit_system)
    _record(
        result,
        "annotation_parsing",
        StageStatus.OK,
        f"{len(result.annotations)} engineering annotations",
    )


def _run_vision(result: AnalysisResult, pdf_path: Path, llm_allowed: bool) -> None:
    if not llm_allowed:
        _record(result, "vision_llm", StageStatus.SKIPPED, "disabled by caller")
        return

    from drawmind.pdf import backend
    from drawmind.pdf.vision import LLMUnavailable, analyze_page_with_vision

    before = len(result.annotations)
    with backend.open_document(pdf_path) as doc:
        num_pages = len(doc)

    # Page by page: one page the provider refuses must not discard the
    # annotations the other pages produced.
    failures: list[str] = []
    for page_idx in range(num_pages):
        try:
            result.annotations = analyze_page_with_vision(
                str(pdf_path),
                page_idx,
                result.annotations,
                unit_system=result.unit_system,
            )
        except LLMUnavailable as exc:
            _record(result, "vision_llm", StageStatus.SKIPPED, str(exc))
            return
        except Exception as exc:
            logger.warning(f"Vision analysis failed on page {page_idx + 1}: {exc}")
            failures.append(f"page {page_idx + 1}: {exc}")

    gained = len(result.annotations) - before
    if not failures:
        _record(result, "vision_llm", StageStatus.OK, f"{gained} additional annotations")
    elif len(failures) == num_pages:
        _record(result, "vision_llm", StageStatus.FAILED, "; ".join(failures))
    else:
        _record(
            result,
            "vision_llm",
            StageStatus.PARTIAL,
            f"{gained} additional annotations, "
            f"{len(failures)} of {num_pages} pages failed: {'; '.join(failures)}",
        )


_HOLE_SIZE_TYPES = frozenset(
    {
        AnnotationType.DIAMETER,
        AnnotationType.THREAD,
        AnnotationType.HOLE_CALLOUT,
        AnnotationType.COUNTERBORE,
        AnnotationType.COUNTERSINK,
    }
)


def _recheck_units(result: AnalysisResult, pdf_path: Path, llm_allowed: bool) -> None:
    """Revisit the unit system once the callout values are known.

    Drawings whose text layer carries no unit evidence are classified metric
    by default. A part whose hole diameters are almost all below 1.5 mm is not
    a real part, so the values themselves settle it. A declared unit or one
    the caller supplied is never overridden, and only hole diameters count:
    depths and surface-finish values are small on metric drawings too.
    """
    from drawmind.pdf.parser import parse_annotations

    if result.unit_system != "metric" or not result.annotations:
        return
    if result.unit_source not in ("default", "vision"):
        return

    diameters = []
    for ann in result.annotations:
        if ann.annotation_type not in _HOLE_SIZE_TYPES:
            continue
        value = ann.parsed.get("value") or ann.parsed.get("nominal_diameter")
        value = value if value is not None else ann.parsed.get("diameter")
        try:
            diameters.append(float(value))
        except (TypeError, ValueError):
            continue

    if not diameters or sum(1 for d in diameters if d < 1.5) <= len(diameters) * 0.5:
        return

    result.unit_system = "inch"
    result.unit_source = "value_recheck"
    result.annotations = parse_annotations(result.raw_texts, unit_system="inch")
    _record(result, "unit_recheck", StageStatus.OK, "metric -> inch (values suggest inches)")

    if llm_allowed:
        # The first vision pass was read in the wrong units and has just been
        # discarded; its stage entry must not outlive it.
        result.stages = [s for s in result.stages if s.name != "vision_llm"]
        _run_vision(result, pdf_path, llm_allowed)
        rerun = result.stage("vision_llm")
        if rerun:
            rerun.detail = f"{rerun.detail} (re-run after unit change)"


def _run_leader_lines(result: AnalysisResult, pdf_path: Path) -> None:
    from drawmind.pdf.leader_lines import extract_leader_targets

    try:
        result.annotations = extract_leader_targets(str(pdf_path), result.annotations)
    except Exception as exc:
        logger.warning(f"Leader-line extraction failed: {exc}")
        _record(result, "leader_lines", StageStatus.FAILED, str(exc))
        return

    traced = sum(1 for a in result.annotations if a.parsed.get("leader_target"))
    _record(result, "leader_lines", StageStatus.OK, f"{traced} annotations with a traced target")


def _run_cad(result: AnalysisResult, step_path: Path) -> None:
    from drawmind.cad.feature_extractor import (
        detect_through_holes,
        extract_cylindrical_faces,
        group_coaxial_features,
    )
    from drawmind.cad.step_reader import load_step

    result.shape = load_step(str(step_path))
    features = extract_cylindrical_faces(result.shape)
    result.holes = group_coaxial_features(features)
    result.holes = detect_through_holes(result.shape, result.holes)

    through = sum(1 for h in result.holes if h.is_through_hole)
    _record(
        result,
        "cad_features",
        StageStatus.OK if result.holes else StageStatus.FAILED,
        f"{len(result.holes)} hole groups ({through} through) from {len(features)} faces"
        if result.holes
        else "no cylindrical features found in the model",
    )


def _run_matching(result: AnalysisResult, pdf_path: Path, llm_allowed: bool) -> None:
    from drawmind.matching.matcher import match_annotations_to_features

    llm_report: dict = {}
    matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
        result.annotations,
        result.holes,
        pdf_path=str(pdf_path),
        use_llm_resolver=llm_allowed,
        llm_report=llm_report,
    )
    result.matches = matches
    result.unmatched_annotations = unmatched_ann
    result.unmatched_holes = unmatched_holes

    _record(result, "matching", StageStatus.OK, f"{len(matches)} matched pairs")

    resolved = sum(1 for m in matches if m.evidence.get("source") == "llm_disambiguation")
    failed = llm_report.get("failed_batches", 0)
    if not llm_allowed:
        _record(result, "llm_disambiguation", StageStatus.SKIPPED, "disabled by caller")
    elif llm_report.get("unavailable"):
        _record(result, "llm_disambiguation", StageStatus.SKIPPED, llm_report["unavailable"])
    elif llm_report.get("error") and not llm_report.get("batches"):
        _record(result, "llm_disambiguation", StageStatus.FAILED, llm_report["error"])
    elif failed:
        status = StageStatus.FAILED if failed >= llm_report["batches"] else StageStatus.PARTIAL
        _record(
            result,
            "llm_disambiguation",
            status,
            f"{failed} of {llm_report['batches']} batches failed "
            f"({llm_report.get('error')}); {resolved} matches resolved",
        )
    elif resolved:
        _record(
            result,
            "llm_disambiguation",
            StageStatus.OK,
            f"{resolved} additional matches resolved",
        )
    else:
        _record(
            result,
            "llm_disambiguation",
            StageStatus.SKIPPED,
            "no ambiguous pairs left to resolve",
        )
