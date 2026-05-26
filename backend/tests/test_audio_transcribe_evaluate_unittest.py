"""Audio call worker must transcribe and evaluate on DISTINCT models.

Transcription needs an audio-capable model (audio_transcription call-site);
evaluation is a text judge (chat_text call-site). The worker must not borrow
one model for both stages — that is the bug that 400'd every inside-sales call
when a text-only Azure deployment was selected.
"""

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.evaluators.workers.audio_transcribe_evaluate import (
    audio_transcribe_evaluate,
)
from app.services.evaluators.workers.types import EvaluatorSpec, WorkerContext


class _FakeHttpResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:  # noqa: D401 - test stub
        return None


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str) -> _FakeHttpResponse:
        return _FakeHttpResponse(b"fake-audio-bytes")


class AudioWorkerTwoModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcription_and_evaluation_use_distinct_llms(self):
        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value="[Agent]: hi [Lead]: hello"
        )
        transcription_llm.generate_json = AsyncMock()  # must NOT be used

        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = AsyncMock(
            return_value={"overall_score": 8, "signals": []}
        )
        evaluation_llm.generate_with_audio = AsyncMock()  # must NOT be used

        record = SimpleNamespace(
            recording_url="https://example.test/rec.mp3", activity_id="act-1"
        )
        evaluator = EvaluatorSpec(
            id=uuid.uuid4(),
            name="Sales Audit",
            prompt="Judge this call: {{transcript}}",
            output_schema=[
                {"key": "overall_score", "type": "number", "isMainMetric": True}
            ],
        )
        ctx = WorkerContext(
            record=record,
            evaluators=[evaluator],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"language": "auto"},
        )

        with (
            patch(
                "app.services.evaluators.workers.audio_transcribe_evaluate.httpx.AsyncClient",
                _FakeAsyncClient,
            ),
            patch(
                "app.services.evaluators.workers.audio_transcribe_evaluate.set_usage_call_purpose"
            ),
        ):
            out = await audio_transcribe_evaluate(ctx)

        # Transcription stage runs only on the transcription model.
        transcription_llm.generate_with_audio.assert_awaited_once()
        evaluation_llm.generate_with_audio.assert_not_awaited()

        # Evaluation stage runs only on the evaluation model.
        evaluation_llm.generate_json.assert_awaited_once()
        transcription_llm.generate_json.assert_not_awaited()

        self.assertIn("hello", out.transcript)
        self.assertEqual(len(out.evaluator_outputs), 1)


class AudioWorkerTransliterationTests(unittest.IsolatedAsyncioTestCase):
    def _make_record(self):
        return SimpleNamespace(
            recording_url="https://example.test/rec.mp3", activity_id="act-1"
        )

    def _make_evaluator(self):
        return EvaluatorSpec(
            id=uuid.uuid4(),
            name="Sales Audit",
            prompt="Judge this call: {{transcript}}",
            output_schema=[
                {"key": "overall_score", "type": "number", "isMainMetric": True}
            ],
        )

    async def test_transliterates_when_enabled_and_returns_both_transcripts(self):
        async def fake_generate_json(*, prompt, json_schema, system_prompt=None, **_):
            props = (json_schema or {}).get("properties", {})
            if "normalized_text" in props:
                return {"normalized_text": "namaste, aap kaise ho"}
            return {"overall_score": 80, "signals": []}

        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = fake_generate_json

        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value="नमस्ते, आप कैसे हो"
        )

        ctx = WorkerContext(
            record=self._make_record(),
            evaluators=[self._make_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={
                "transliterate": True,
                "target_script": "latin",
                "script": "devanagari",
                "language": "hi",
            },
        )

        with (
            patch(
                "app.services.evaluators.workers.audio_transcribe_evaluate.httpx.AsyncClient",
                _FakeAsyncClient,
            ),
            patch(
                "app.services.evaluators.workers.audio_transcribe_evaluate.set_usage_call_purpose"
            ),
        ):
            out = await audio_transcribe_evaluate(ctx)

        self.assertEqual(out.transcript, "नमस्ते, आप कैसे हो")
        self.assertEqual(out.transcript_transliterated, "namaste, aap kaise ho")
        self.assertEqual(
            out.transliteration_meta,
            {"enabled": True, "source_script": "devanagari", "target_script": "latin"},
        )

    async def test_no_transliteration_when_disabled(self):
        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = AsyncMock(
            return_value={"overall_score": 8, "signals": []}
        )

        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value="hello world"
        )

        ctx = WorkerContext(
            record=self._make_record(),
            evaluators=[self._make_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"transliterate": False},
        )

        with (
            patch(
                "app.services.evaluators.workers.audio_transcribe_evaluate.httpx.AsyncClient",
                _FakeAsyncClient,
            ),
            patch(
                "app.services.evaluators.workers.audio_transcribe_evaluate.set_usage_call_purpose"
            ),
        ):
            out = await audio_transcribe_evaluate(ctx)

        self.assertIsNone(out.transcript_transliterated)
        self.assertIsNone(out.transliteration_meta)


if __name__ == "__main__":
    unittest.main()
