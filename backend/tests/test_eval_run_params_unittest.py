import uuid
import unittest

from app.services.evaluators.eval_run_params import EvalRunParams


def _base_params(**overrides):
    p = {
        "eval_run_id": uuid.uuid4(),
        "app_id": "inside-sales",
        "dataset_id": "calls",
        "run_name": "t",
        "selection": {"mode": "all"},
        "evaluator_ids": [uuid.uuid4()],
        "transcription_llm_config": {"provider": "vertex", "model": "gemini-3.1-pro-preview"},
        "evaluation_llm_config": {"provider": "azure_openai", "model": "ai-evals-gpt-5.4"},
        "transcription_config": {"transliterate": True, "target_script": "latin"},
    }
    p.update(overrides)
    return p


class EvalRunParamsTwoModelTests(unittest.TestCase):
    def test_accepts_separate_models_and_transliteration(self):
        params = EvalRunParams.model_validate(_base_params())
        self.assertEqual(params.transcription_llm_config.model, "gemini-3.1-pro-preview")
        self.assertEqual(params.evaluation_llm_config.model, "ai-evals-gpt-5.4")
        self.assertTrue(params.transcription_config.transliterate)
        self.assertEqual(params.transcription_config.target_script, "latin")

    def test_rejects_legacy_single_llm_config_key(self):
        bad = _base_params()
        bad.pop("evaluation_llm_config")
        bad["llm_config"] = {"provider": "azure_openai", "model": "ai-evals-gpt-5.4"}
        with self.assertRaises(Exception):
            EvalRunParams.model_validate(bad)

    def test_rejects_dead_transcription_model_field(self):
        bad = _base_params()
        bad["transcription_config"] = {"model": "gemini"}
        with self.assertRaises(Exception):
            EvalRunParams.model_validate(bad)


if __name__ == "__main__":
    unittest.main()
