import os
import sys
import unittest
from types import ModuleType, SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

fake_database = ModuleType('app.database')
fake_database.get_db = None
sys.modules.setdefault('app.database', fake_database)

from app.config import settings
from app.routes import admin as admin_routes


class InviteLinkUrlTests(unittest.TestCase):
    def test_invite_base_url_prefers_request_origin(self):
        request = SimpleNamespace(headers={'origin': 'http://192.168.10.188:5173'})

        base_url = admin_routes._invite_base_url(request)

        self.assertEqual(base_url, 'http://192.168.10.188:5173')

    def test_invite_base_url_falls_back_to_config(self):
        request = SimpleNamespace(headers={})
        original_base_url = settings.APP_BASE_URL
        settings.APP_BASE_URL = 'http://localhost:5173/'
        try:
            base_url = admin_routes._invite_base_url(request)
        finally:
            settings.APP_BASE_URL = original_base_url

        self.assertEqual(base_url, 'http://localhost:5173')
