"""Audio call worker: transcribe + (optional) transliterate + evaluate on DISTINCT models.

Transcription needs an audio-capable model (audio_transcription call-site);
evaluation is the text judge (chat_text call-site), which also runs the optional
transliteration pass. Every stage returns STRUCTURED output — no free-form text
extraction. Transliteration is gated on the script the transcription model reports
(detected_script), so a transcript already in the target script skips the LLM call.
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

    def raise_for_status(self) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, _url: str) -> _FakeHttpResponse:
        return _FakeHttpResponse(b"fake-audio-bytes")


def _evaluator() -> EvaluatorSpec:
    return EvaluatorSpec(
        id=uuid.uuid4(),
        name="Sales Audit",
        prompt="Judge this call: {{transcript}}",
        output_schema=[{"key": "overall_score", "type": "number", "isMainMetric": True}],
    )


def _record():
    return SimpleNamespace(recording_url="https://example.test/rec.mp3", activity_id="act-1")


_PATCH_HTTP = "app.services.evaluators.workers.audio_transcribe_evaluate.httpx.AsyncClient"
_PATCH_USAGE = "app.services.evaluators.workers.audio_transcribe_evaluate.set_usage_call_purpose"


class AudioWorkerTwoModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcription_and_evaluation_use_distinct_llms(self):
        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value={"transcript": "[Agent]: hi [Lead]: hello", "detected_script": "latin"}
        )
        transcription_llm.generate_json = AsyncMock()  # must NOT be used

        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = AsyncMock(return_value={"overall_score": 8, "signals": []})
        evaluation_llm.generate_with_audio = AsyncMock()  # must NOT be used

        ctx = WorkerContext(
            record=_record(),
            evaluators=[_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"language": "Auto-detect"},
        )

        with patch(_PATCH_HTTP, _FakeAsyncClient), patch(_PATCH_USAGE):
            out = await audio_transcribe_evaluate(ctx)

        transcription_llm.generate_with_audio.assert_awaited_once()
        evaluation_llm.generate_with_audio.assert_not_awaited()
        evaluation_llm.generate_json.assert_awaited_once()  # eval only — no transliteration
        transcription_llm.generate_json.assert_not_awaited()

        self.assertIn("hello", out.transcript)
        self.assertEqual(len(out.evaluator_outputs), 1)

    async def test_transcription_requests_structured_output(self):
        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value={"transcript": "hello world", "detected_script": "latin"}
        )
        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = AsyncMock(return_value={"overall_score": 7, "signals": []})

        ctx = WorkerContext(
            record=_record(),
            evaluators=[_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"language": "English"},
        )

        with patch(_PATCH_HTTP, _FakeAsyncClient), patch(_PATCH_USAGE):
            await audio_transcribe_evaluate(ctx)

        _, kwargs = transcription_llm.generate_with_audio.call_args
        self.assertIn("json_schema", kwargs)
        props = kwargs["json_schema"]["properties"]
        self.assertIn("transcript", props)
        self.assertIn("detected_script", props)


class AudioWorkerTransliterationTests(unittest.IsolatedAsyncioTestCase):
    async def test_transliterates_when_detected_differs_from_target(self):
        async def fake_generate_json(*, prompt, json_schema, system_prompt=None, **_):
            props = (json_schema or {}).get("properties", {})
            if "normalized_text" in props:
                return {"normalized_text": "namaste, aap kaise ho"}
            return {"overall_score": 80, "signals": []}

        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = fake_generate_json

        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value={"transcript": "नमस्ते, आप कैसे हो", "detected_script": "devanagari"}
        )

        ctx = WorkerContext(
            record=_record(),
            evaluators=[_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"transliterate": True, "target_script": "latin", "language": "Hindi"},
        )

        with patch(_PATCH_HTTP, _FakeAsyncClient), patch(_PATCH_USAGE):
            out = await audio_transcribe_evaluate(ctx)

        self.assertEqual(out.transcript, "नमस्ते, आप कैसे हो")
        self.assertEqual(out.transcript_transliterated, "namaste, aap kaise ho")
        self.assertEqual(
            out.transliteration_meta,
            {"enabled": True, "source_script": "devanagari", "target_script": "latin"},
        )

    async def test_skips_transliteration_when_already_in_target_script(self):
        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = AsyncMock(return_value={"overall_score": 8, "signals": []})

        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value={"transcript": "hello how are you", "detected_script": "latin"}
        )

        ctx = WorkerContext(
            record=_record(),
            evaluators=[_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"transliterate": True, "target_script": "latin", "language": "English"},
        )

        with patch(_PATCH_HTTP, _FakeAsyncClient), patch(_PATCH_USAGE):
            out = await audio_transcribe_evaluate(ctx)

        # Already in the target script → no transliteration call; generate_json used once (eval).
        self.assertIsNone(out.transcript_transliterated)
        self.assertIsNone(out.transliteration_meta)
        evaluation_llm.generate_json.assert_awaited_once()

    async def test_no_transliteration_when_disabled(self):
        evaluation_llm = MagicMock()
        evaluation_llm.generate_json = AsyncMock(return_value={"overall_score": 8, "signals": []})

        transcription_llm = MagicMock()
        transcription_llm.generate_with_audio = AsyncMock(
            return_value={"transcript": "नमस्ते", "detected_script": "devanagari"}
        )

        ctx = WorkerContext(
            record=_record(),
            evaluators=[_evaluator()],
            transcription_llm=transcription_llm,
            evaluation_llm=evaluation_llm,
            transcription_config={"transliterate": False},
        )

        with patch(_PATCH_HTTP, _FakeAsyncClient), patch(_PATCH_USAGE):
            out = await audio_transcribe_evaluate(ctx)

        self.assertIsNone(out.transcript_transliterated)
        self.assertIsNone(out.transliteration_meta)


if __name__ == "__main__":
    unittest.main()
