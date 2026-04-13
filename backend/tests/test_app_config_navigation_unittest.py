import unittest

from app.schemas.app_config import AppConfig


class AppConfigNavigationTests(unittest.TestCase):
    def test_app_config_accepts_navigation_metadata(self):
        config = AppConfig.model_validate(
            {
                'displayName': 'Kaira Bot',
                'icon': '/kaira-icon.svg',
                'description': 'Health chat bot assistant',
                'navigation': {
                    'homePath': '/kaira',
                    'ownedPathPrefixes': ['/kaira'],
                    'settingsPath': '/kaira/settings',
                    'logsPath': '/kaira/logs',
                    'runsPath': '/kaira/runs',
                    'runDetailPath': '/kaira/runs/:runId',
                    'threadDetailPath': '/kaira/threads/:threadId',
                },
            }
        )

        self.assertEqual(config.navigation.home_path, '/kaira')
        self.assertEqual(config.navigation.owned_path_prefixes, ['/kaira'])
        self.assertEqual(config.navigation.thread_detail_path, '/kaira/threads/:threadId')

    def test_navigation_defaults_allow_missing_optional_paths(self):
        config = AppConfig.model_validate(
            {
                'displayName': 'Voice Rx',
                'icon': '/voice-rx-icon.jpeg',
                'description': 'Audio file evaluation tool',
            }
        )

        self.assertEqual(config.navigation.home_path, '/')
        self.assertEqual(config.navigation.owned_path_prefixes, [])
        self.assertIsNone(config.navigation.thread_detail_path)
