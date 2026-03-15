"""PDF text extraction with bounding boxes using PyMuPDF."""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from drawmind.config import MIN_TEXT_COUNT_FOR_NATIVE


def _has_engineering_content(texts: list[dict]) -> bool:
    """Check if extracted text contains recognizable engineering annotations.

    Vector PDFs with custom fonts may extract text but yield mostly garbage
    (replacement chars \ufffd) rather than usable engineering annotations.
    """
    if not texts:
        return False

    engineering_patterns = [
        r'M\d+',           # Thread: M10, M8
        r'[\u2300\u00d8]\s*\d',  # Diameter: Ø10, ⌀8
        r'\b(?:THRU|DEPTH|DEEP|CBORE|CSINK)\b',
        r'\d+\s*[xX\u00d7]\s',  # Multiplier: 4x, 6X
        r'[A-Z]\d{1,2}\s*/\s*[a-z]\d',  # Fit: H7/g6
    ]

    total_chars = sum(len(t["text"]) for t in texts)
    replacement_chars = sum(t["text"].count('\ufffd') for t in texts)

    # If >30% of characters are replacement chars, text is corrupted
    if total_chars > 0 and replacement_chars / total_chars > 0.3:
        return False

    combined = " ".join(t["text"] for t in texts)
    for pat in engineering_patterns:
        if re.search(pat, combined, re.IGNORECASE):
            return True

    return False


def extract_all_text(pdf_path: str | Path) -> list[dict]:
    """Extract all text elements with bounding boxes from a PDF.

    Tries native text extraction first. Falls back to OCR when:
    - Native extraction yields too few text elements (scanned PDF)
    - Native text is corrupted (custom fonts → replacement characters)
    - Native text has no recognizable engineering annotations

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of dicts with keys: text, bbox, font, size, page, source
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    all_texts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_texts = _extract_page_native(page, page_num)

        needs_ocr = False
        if len(page_texts) < MIN_TEXT_COUNT_FOR_NATIVE:
            needs_ocr = True
        elif not _has_engineering_content(page_texts):
            # Native text exists but is corrupted or has no engineering content
            needs_ocr = True

        if needs_ocr:
            ocr_texts = _extract_page_ocr(page, page_num)
            if _has_engineering_content(ocr_texts):
                # OCR found engineering content — merge with native
                page_texts = _merge_text_sources(page_texts, ocr_texts)
            elif len(ocr_texts) > len(page_texts):
                page_texts = ocr_texts

        all_texts.extend(page_texts)

    doc.close()
    return all_texts


def _merge_text_sources(native: list[dict], ocr: list[dict]) -> list[dict]:
    """Merge native and OCR text, preferring OCR for engineering annotations.

    Keeps native text that doesn't overlap with OCR, and adds all OCR text.
    This handles the case where native text has some valid content (title block)
    but engineering annotations are only readable via OCR.
    """
    # Simple strategy: use OCR as primary, add non-overlapping native text
    merged = list(ocr)

    for n_item in native:
        n_cx = (n_item["bbox"]["x0"] + n_item["bbox"]["x1"]) / 2
        n_cy = (n_item["bbox"]["y0"] + n_item["bbox"]["y1"]) / 2
        has_overlap = False

        for o_item in ocr:
            if n_item["page"] != o_item["page"]:
                continue
            o_cx = (o_item["bbox"]["x0"] + o_item["bbox"]["x1"]) / 2
            o_cy = (o_item["bbox"]["y0"] + o_item["bbox"]["y1"]) / 2
            dist = ((n_cx - o_cx) ** 2 + (n_cy - o_cy) ** 2) ** 0.5
            if dist < 20:  # Close enough to be the same text
                has_overlap = True
                break

        if not has_overlap and '\ufffd' not in n_item["text"]:
            merged.append(n_item)

    return merged


def _extract_page_native(page: fitz.Page, page_num: int) -> list[dict]:
    """Extract text natively from a PDF page."""
    texts = []
    text_dict = page.get_text("dict")

    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:  # text block only
            continue

        for line in block.get("lines", []):
            line_text = ""
            spans_data = []

            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue

                spans_data.append(span)
                line_text += span["text"]

            line_text = line_text.strip()
            if not line_text:
                continue

            # Use the line-level bbox
            bbox = line.get("bbox", (0, 0, 0, 0))
            font = spans_data[0].get("font", "") if spans_data else ""
            size = spans_data[0].get("size", 0) if spans_data else 0

            texts.append({
                "text": line_text,
                "bbox": {
                    "x0": bbox[0],
                    "y0": bbox[1],
                    "x1": bbox[2],
                    "y1": bbox[3],
                },
                "font": font,
                "size": size,
                "page": page_num,
                "source": "native",
            })

    return texts


def _extract_page_ocr(page: fitz.Page, page_num: int) -> list[dict]:
    """Extract text from a page using OCR.

    Tries Tesseract first (better for engineering drawings with sparse text),
    then falls back to PyMuPDF's built-in OCR.
    """
    # Try Tesseract first (PSM 11 = sparse text, better for drawings)
    texts = _extract_page_tesseract(page, page_num)
    if texts:
        return texts

    # Fallback: PyMuPDF built-in OCR
    try:
        tp = page.get_textpage_ocr(flags=0, dpi=300)
        text_dict = page.get_text("dict", textpage=tp)

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue

            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    line_text += span.get("text", "")

                line_text = line_text.strip()
                if not line_text:
                    continue

                bbox = line.get("bbox", (0, 0, 0, 0))
                texts.append({
                    "text": line_text,
                    "bbox": {
                        "x0": bbox[0],
                        "y0": bbox[1],
                        "x1": bbox[2],
                        "y1": bbox[3],
                    },
                    "font": "",
                    "size": 0,
                    "page": page_num,
                    "source": "ocr",
                })

    except Exception:
        pass

    return texts


def _extract_page_tesseract(page: fitz.Page, page_num: int) -> list[dict]:
    """Extract text from a page using Tesseract OCR (sparse text mode).

    Returns empty list if Tesseract is not available.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        return []

    from drawmind.config import OCR_DPI, OCR_CONFIDENCE_THRESHOLD

    try:
        pix = page.get_pixmap(dpi=OCR_DPI)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        data = pytesseract.image_to_data(
            img,
            output_type=pytesseract.Output.DICT,
            config="--psm 11 --oem 3",
        )

        scale = 72.0 / OCR_DPI
        texts = []

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])

            if text and conf > OCR_CONFIDENCE_THRESHOLD:
                texts.append({
                    "text": text,
                    "bbox": {
                        "x0": data["left"][i] * scale,
                        "y0": data["top"][i] * scale,
                        "x1": (data["left"][i] + data["width"][i]) * scale,
                        "y1": (data["top"][i] + data["height"][i]) * scale,
                    },
                    "font": "",
                    "size": 0,
                    "page": page_num,
                    "source": "ocr_tesseract",
                    "confidence": conf / 100.0,
                })

        return texts

    except Exception:
        return []


def get_page_as_image(pdf_path: str | Path, page_num: int = 0, dpi: int = 300) -> bytes:
    """Render a PDF page as a PNG image (for vision LLM).

    Returns:
        PNG image bytes
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


def detect_unit_system(pdf_path: str | Path) -> str:
    """Detect the unit system used in a technical drawing PDF.

    Checks explicit unit declarations first, then uses heuristics on
    dimension values (e.g., Ø.438 patterns indicate inches).

    Returns:
        "inch" or "metric"
    """
    doc = fitz.open(str(pdf_path))
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    # 1. Explicit metric declarations (strongest signal)
    metric_patterns = [
        r'UNITS?\s*:\s*(?:MM|MILLIMETERS?)',
        r'ALL\s+DIMENSIONS\s+(?:IN\s+)?(?:MM|MILLIMETERS?)',
        r'DIMENSIONS\s+(?:ARE\s+)?IN\s+(?:MM|MILLIMETERS?)',
        r'MILLIMETERS?\s+UNLESS',
    ]
    for pat_str in metric_patterns:
        if re.search(pat_str, full_text, re.IGNORECASE):
            return "metric"

    # 2. Explicit inch declarations
    inch_patterns = [
        r'UNITS?\s*:\s*INCH',
        r'DIMENSIONING\s+IN\s+INCH',
        r'ALL\s+DIMENSIONS\s+IN\s+INCH',
        r'DIMENSIONS\s+ARE\s+IN\s+INCH',
        r'INCH(?:ES)?\s+UNLESS',
    ]
    for pat_str in inch_patterns:
        if re.search(pat_str, full_text, re.IGNORECASE):
            return "inch"

    # UNC/UNEF thread specs are exclusively imperial
    unc_pattern = re.compile(r'\d+/\d+-\d+\s*(?:UNC|UNF|UNEF)', re.IGNORECASE)
    if unc_pattern.search(full_text):
        return "inch"

    # 3. Implicit inch detection via dimension value patterns
    # Inch drawings commonly use .XXX format (e.g., Ø.438, .250 THRU)
    # Only count values preceded by a diameter symbol or at start of dimension —
    # NOT values inside tolerances (+.025/-.010)
    inch_dim_pattern = re.compile(
        r'(?:^|[\u00d8\u2300\u2205\s])\.(\d{2,4})\b'  # .438, .250 (preceded by Ø or whitespace)
    )
    inch_vals = []
    for m in inch_dim_pattern.finditer(full_text):
        # Check if preceded by + or - (tolerance, not dimension)
        prefix_start = max(0, m.start() - 3)
        prefix = full_text[prefix_start:m.start()]
        if not re.search(r'[+\-]', prefix):
            inch_vals.append(m.group(1))

    # If we find >=2 decimal-inch style dimensions, classify as inch
    if len(inch_vals) >= 2:
        return "inch"

    # 4. Heuristic: if most dimension values are small (< 2.0) and none > 25,
    # it's likely an inch drawing where the text was poorly extracted
    dim_pattern = re.compile(r'(\d{1,3}\.?\d{0,4})')
    all_dims = []
    for m in dim_pattern.finditer(full_text):
        try:
            v = float(m.group(1))
            if 0.05 < v < 200:  # Filter out noise
                all_dims.append(v)
        except ValueError:
            pass
    if len(all_dims) >= 3:
        small_count = sum(1 for d in all_dims if d < 2.0)
        large_count = sum(1 for d in all_dims if d > 25.0)
        if small_count > len(all_dims) * 0.6 and large_count == 0:
            return "inch"

    # 5. Fallback: use Vision LLM to detect unit system from drawing image
    try:
        from drawmind.config import USE_VISION_LLM
        if USE_VISION_LLM:
            unit = _detect_unit_system_vision(pdf_path)
            if unit:
                return unit
    except Exception:
        pass

    return "metric"


def _detect_unit_system_vision(pdf_path: str | Path) -> str | None:
    """Use Vision LLM to detect unit system from drawing title block."""
    try:
        from drawmind.llm.client import get_llm_client
        client = get_llm_client()
        if not client.available:
            return None

        img_bytes = get_page_as_image(pdf_path, page_num=0, dpi=100)
        result = client.complete_json(
            'Look at this technical drawing. What unit system is used? '
            'Check the title block, notes, or dimension format. '
            'Inch drawings use values like .250, .438, 1/4-20 UNC. '
            'Metric drawings use values like 10.0, M8, Ø20. '
            'Return JSON: {"unit_system": "inch" or "metric", "evidence": "brief reason"}',
            images=[img_bytes],
        )

        if isinstance(result, dict):
            unit = result.get("unit_system", "").lower()
            if unit in ("inch", "metric"):
                import logging
                logging.getLogger(__name__).info(
                    f"Vision LLM detected unit system: {unit} ({result.get('evidence', '')})"
                )
                return unit
    except Exception:
        pass
    return None


def get_page_dimensions(pdf_path: str | Path, page_num: int = 0) -> tuple[float, float]:
    """Get page dimensions in points.

    Returns:
        (width, height) in points
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_num]
    rect = page.rect
    doc.close()
    return rect.width, rect.height
