"""An empty provider answer must be retried, not passed on as a result."""

import unittest

from drawmind.llm.client import EmptyCompletion, _require_content


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, choices):
        self.choices = choices


class TestRequireContent(unittest.TestCase):
    def test_normal_content_passes_through(self):
        self.assertEqual(_require_content(_Response([_Choice('{"a": 1}')])), '{"a": 1}')

    def test_empty_string_raises(self):
        with self.assertRaises(EmptyCompletion):
            _require_content(_Response([_Choice("")]))

    def test_whitespace_only_raises(self):
        with self.assertRaises(EmptyCompletion):
            _require_content(_Response([_Choice("   \n ")]))

    def test_none_content_raises(self):
        with self.assertRaises(EmptyCompletion):
            _require_content(_Response([_Choice(None)]))

    def test_no_choices_raises(self):
        with self.assertRaises(EmptyCompletion):
            _require_content(_Response([]))

    def test_finish_reason_is_reported(self):
        """Why the answer was empty decides whether it is worth retrying."""
        with self.assertRaises(EmptyCompletion) as ctx:
            _require_content(_Response([_Choice(None, finish_reason="content_filter")]))
        self.assertIn("content_filter", str(ctx.exception))


class TestRetryBehaviour(unittest.TestCase):
    def test_empty_completion_is_retried_then_succeeds(self):
        from drawmind.llm import client as client_module

        calls = {"n": 0}

        class _FakeCompletions:
            def create(self, **kwargs):
                calls["n"] += 1
                if calls["n"] < 3:
                    return _Response([_Choice("", finish_reason="length")])
                return _Response([_Choice("recovered")])

        class _FakeClient:
            chat = type("chat", (), {"completions": _FakeCompletions()})()

        llm = client_module.LLMClient()
        llm._client = _FakeClient()

        original_sleep = client_module.time.sleep
        client_module.time.sleep = lambda _s: None
        try:
            result = llm.complete("prompt")
        finally:
            client_module.time.sleep = original_sleep

        self.assertEqual(result, "recovered")
        self.assertEqual(calls["n"], 3)

    def test_persistent_emptiness_raises(self):
        from drawmind.llm import client as client_module

        class _FakeCompletions:
            def create(self, **kwargs):
                return _Response([_Choice(None, finish_reason="content_filter")])

        class _FakeClient:
            chat = type("chat", (), {"completions": _FakeCompletions()})()

        llm = client_module.LLMClient()
        llm._client = _FakeClient()

        original_sleep = client_module.time.sleep
        client_module.time.sleep = lambda _s: None
        try:
            with self.assertRaises(EmptyCompletion):
                llm.complete("prompt")
        finally:
            client_module.time.sleep = original_sleep


class TestCompleteJson(unittest.TestCase):
    """An answer that arrives but carries no JSON gets its own retry."""

    def _client_returning(self, bodies):
        from drawmind.llm import client as client_module

        state = {"i": 0}

        class _FakeCompletions:
            def create(self, **kwargs):
                body = bodies[min(state["i"], len(bodies) - 1)]
                state["i"] += 1
                return _Response([_Choice(body)])

        class _FakeClient:
            chat = type("chat", (), {"completions": _FakeCompletions()})()

        llm = client_module.LLMClient()
        llm._client = _FakeClient()
        return llm, state

    def _no_sleep(self):
        from drawmind.llm import client as client_module

        original = client_module.time.sleep
        client_module.time.sleep = lambda _s: None
        return original

    def test_plain_json_parses(self):
        llm, _ = self._client_returning(['{"a": 1}'])
        self.assertEqual(llm.complete_json("p"), {"a": 1})

    def test_fenced_json_parses(self):
        llm, _ = self._client_returning(['```json\n[{"b": 2}]\n```'])
        self.assertEqual(llm.complete_json("p"), [{"b": 2}])

    def test_empty_fence_is_retried(self):
        """An empty code fence used to surface as a JSON syntax error."""
        from drawmind.llm import client as client_module

        llm, state = self._client_returning(["```json\n\n```", '{"ok": true}'])
        original = self._no_sleep()
        try:
            self.assertEqual(llm.complete_json("p"), {"ok": True})
        finally:
            client_module.time.sleep = original
        self.assertEqual(state["i"], 2)

    def test_malformed_json_is_reported_not_retried(self):
        """Broken syntax is a model problem; repeating it just costs money."""
        from drawmind.llm import client as client_module

        llm, state = self._client_returning(["{not json"])
        original = self._no_sleep()
        try:
            with self.assertRaises(ValueError):
                llm.complete_json("p")
        finally:
            client_module.time.sleep = original
        self.assertEqual(state["i"], 1)


class TestNothingToExtract(unittest.TestCase):
    """A page with no callouts may answer in prose; a broken call must not."""

    def setUp(self):
        from drawmind.pdf.vision import _states_nothing_to_extract

        self.detect = _states_nothing_to_extract

    def test_accepts_observed_refusals(self):
        for text in (
            "I am sorry, but I cannot fulfill this request. The provided image is a "
            "general notes page and an isometric view without any specific hole "
            "callouts or dimensions. Therefore, there are no hole-related annotations "
            "to extract.",
            "I am sorry, but I cannot fulfill this request. The provided image is a "
            "blank engineering drawing with only notes and references. Therefore, "
            "there are no hole annotations to extract.",
            "There are no hole callouts present on this page.",
        ):
            with self.subTest(text=text[:40]):
                self.assertTrue(self.detect(text))

    def test_rejects_anything_that_is_not_a_statement_about_holes(self):
        for text in (
            "I cannot help with that request.",
            "Error: rate limit exceeded, please retry later.",
            "The drawing shows 4 holes but I will not list them.",
            "",
            "x" * 2000,
        ):
            with self.subTest(text=text[:40]):
                self.assertFalse(self.detect(text))


if __name__ == "__main__":
    unittest.main()
