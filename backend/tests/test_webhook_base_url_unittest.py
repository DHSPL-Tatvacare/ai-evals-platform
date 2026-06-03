"""Provider webhook URLs render the single branded APP_BASE_URL, never the request Origin.

Regression guard: the raw container FQDN once leaked into a saved WATI webhook
because ``resolve_base_url`` reflected whatever host the operator browsed from.
The webhook base is now always ``APP_BASE_URL`` — one branded source of truth.
"""
import unittest

from app.config import settings
from app.services.orchestration.api.connections import resolve_base_url


class ResolveWebhookBaseUrlTest(unittest.TestCase):
    def setUp(self):
        self._app = settings.APP_BASE_URL

    def tearDown(self):
        settings.APP_BASE_URL = self._app

    def test_uses_app_base_url(self):
        settings.APP_BASE_URL = "https://evals.tatvacare.in/"
        self.assertEqual(resolve_base_url(None), "https://evals.tatvacare.in")

    def test_ignores_request_origin(self):
        # Operator browsing the raw container host must NOT change the webhook URL.
        settings.APP_BASE_URL = "https://evals.tatvacare.in"
        self.assertEqual(
            resolve_base_url("https://ai-evals-fe-prod.nicerock.azurecontainerapps.io"),
            "https://evals.tatvacare.in",
        )


if __name__ == "__main__":
    unittest.main()
