"""Tests for the shared pipeline entry point."""

import unittest
from pathlib import Path

from drawmind.pipeline import Settings, StageStatus, analyze

EXAMPLE = Path(__file__).parent.parent / "examples" / "SYN-01-SimpleBlock"
PDF = EXAMPLE / "drawing.pdf"
STEP = EXAMPLE / "model.stp"

# A case whose drawing spans several pages, for per-page failure handling.
MULTIPAGE = Path(__file__).parent.parent / "examples" / "D2MI-904"
MULTIPAGE_PDF = MULTIPAGE / "drawing.pdf"
MULTIPAGE_STEP = next(MULTIPAGE.glob("model.st*"), MULTIPAGE / "model.stp")


class NetworkUsed(AssertionError):
    pass


def _forbid_network():
    """Replace the provider constructor so any outbound call fails loudly."""
    import openai

    import drawmind.llm.client as client_module

    original = openai.OpenAI
    client_module._client = None

    def refuse(*args, **kwargs):
        raise NetworkUsed("the pipeline tried to reach a model provider")

    openai.OpenAI = refuse
    return original


def _restore_network(original):
    import openai

    import drawmind.llm.client as client_module

    openai.OpenAI = original
    client_module._client = None


@unittest.skipUnless(PDF.exists() and STEP.exists(), "example files not present")
class TestOfflineGuarantee(unittest.TestCase):
    """use_llm=False must mean nothing leaves the machine."""

    def setUp(self):
        import drawmind.config as config

        self._original_openai = _forbid_network()
        # A configured key must not be what keeps the run offline; the
        # caller's setting has to be the only thing that does.
        self._original_flag = config.USE_VISION_LLM
        config.USE_VISION_LLM = True

    def tearDown(self):
        import drawmind.config as config

        config.USE_VISION_LLM = self._original_flag
        _restore_network(self._original_openai)

    def test_no_llm_contacts_no_provider(self):
        result = analyze(PDF, STEP, settings=Settings(use_llm=False))

        self.assertFalse(result.llm_used)
        self.assertEqual(result.stage("vision_llm").status, StageStatus.SKIPPED)
        self.assertEqual(result.stage("llm_disambiguation").status, StageStatus.SKIPPED)

    def test_unit_detection_receives_the_caller_setting(self):
        from drawmind.pdf import extractor

        seen = []
        original = extractor.detect_unit_system

        def spy(pdf_path, use_llm=False, report=None):
            seen.append(use_llm)
            return original(pdf_path, use_llm=use_llm, report=report)

        extractor.detect_unit_system = spy
        try:
            analyze(PDF, STEP, settings=Settings(use_llm=False))
        finally:
            extractor.detect_unit_system = original

        self.assertEqual(seen, [False])

    def test_no_llm_still_produces_a_result(self):
        result = analyze(PDF, STEP, settings=Settings(use_llm=False))

        self.assertGreater(len(result.holes), 0)
        self.assertEqual(result.stage("cad_features").status, StageStatus.OK)

    def test_unit_override_skips_detection_fallback(self):
        result = analyze(PDF, STEP, settings=Settings(use_llm=False, unit_system="inch"))

        self.assertEqual(result.unit_system, "inch")
        self.assertIn("caller-supplied", result.stage("unit_detection").detail)


@unittest.skipUnless(
    PDF.exists() and STEP.exists() and MULTIPAGE_PDF.exists() and MULTIPAGE_STEP.exists(),
    "example files not present",
)
class TestStageReporting(unittest.TestCase):
    def test_vision_failure_is_not_reported_as_enhancement(self):
        import drawmind.config as config
        from drawmind.pdf import vision

        original_flag = config.USE_VISION_LLM
        original_vision = vision.analyze_page_with_vision

        def explode(*args, **kwargs):
            raise RuntimeError("provider returned 502")

        config.USE_VISION_LLM = True
        vision.analyze_page_with_vision = explode
        try:
            result = analyze(PDF, STEP, settings=Settings(use_llm=True))
        finally:
            vision.analyze_page_with_vision = original_vision
            config.USE_VISION_LLM = original_flag

        stage = result.stage("vision_llm")
        self.assertEqual(stage.status, StageStatus.FAILED)
        self.assertIn("502", stage.detail)
        self.assertFalse(result.llm_used)
        self.assertTrue(any("vision_llm" in w for w in result.warnings))

    def test_one_failing_page_does_not_discard_the_others(self):
        """A provider refusing page 2 must not lose what pages 1 and 3 produced."""
        import drawmind.config as config
        from drawmind.pdf import vision

        original_flag = config.USE_VISION_LLM
        original_vision = vision.analyze_page_with_vision
        seen = []

        def flaky(pdf_path, page_num, existing, unit_system="metric"):
            seen.append(page_num)
            if page_num == 0:
                raise RuntimeError("provider returned empty content")
            return existing

        config.USE_VISION_LLM = True
        vision.analyze_page_with_vision = flaky
        try:
            result = analyze(MULTIPAGE_PDF, MULTIPAGE_STEP, settings=Settings(use_llm=True))
        finally:
            vision.analyze_page_with_vision = original_vision
            config.USE_VISION_LLM = original_flag

        stage = result.stage("vision_llm")
        self.assertGreater(len(seen), 1, "every page must be attempted")
        self.assertEqual(sorted(seen), list(range(len(seen))))
        self.assertEqual(stage.status, StageStatus.PARTIAL)
        self.assertIn("page 1", stage.detail)
        self.assertTrue(result.llm_used, "a partial vision pass still contributed")

    def test_every_stage_is_recorded(self):
        result = analyze(PDF, STEP, settings=Settings(use_llm=False))

        recorded = {s.name for s in result.stages}
        for expected in (
            "text_extraction",
            "ocr",
            "unit_detection",
            "annotation_parsing",
            "vision_llm",
            "leader_lines",
            "cad_features",
            "matching",
            "llm_disambiguation",
        ):
            self.assertIn(expected, recorded)


class TestInputValidation(unittest.TestCase):
    def test_missing_pdf_raises(self):
        with self.assertRaises(FileNotFoundError):
            analyze("does-not-exist.pdf", STEP)

    @unittest.skipUnless(PDF.exists(), "example files not present")
    def test_missing_step_raises(self):
        with self.assertRaises(FileNotFoundError):
            analyze(PDF, "does-not-exist.stp")

    @unittest.skipUnless(PDF.exists() and STEP.exists(), "example files not present")
    def test_page_limit_is_enforced(self):
        import drawmind.config as config

        original = config.MAX_PDF_PAGES
        config.MAX_PDF_PAGES = 0
        try:
            with self.assertRaises(ValueError) as ctx:
                analyze(PDF, STEP, settings=Settings(use_llm=False))
            self.assertIn("MAX_PDF_PAGES", str(ctx.exception))
        finally:
            config.MAX_PDF_PAGES = original


if __name__ == "__main__":
    unittest.main()
