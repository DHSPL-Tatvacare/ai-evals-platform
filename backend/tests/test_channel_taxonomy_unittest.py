"""channel_taxonomy derives {channel: providers} from node x-providers declarations."""
import ast
import os
import unittest

from app.services.orchestration import channel_taxonomy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
from app.services.orchestration.nodes.messaging_send_whatsapp_template import (
    _Config as WhatsAppConfig,
)
from app.services.orchestration.nodes.voice_place_call import _Config as VoiceConfig


def _declared_providers(config_cls) -> list[str]:
    """Read x-providers straight off the node's connection_id field — the same
    declaration channel_provider_map must derive from (no literal duplication)."""
    field = config_cls.model_fields["connection_id"]
    return list(field.json_schema_extra["x-providers"])


class ChannelProviderMapTest(unittest.TestCase):
    def test_whatsapp_providers_match_node_declaration(self):
        declared = _declared_providers(WhatsAppConfig)
        self.assertIn("wati", declared)
        self.assertIn("aisensy", declared)
        mapped = channel_taxonomy.channel_provider_map()
        self.assertIn("whatsapp", mapped)
        self.assertEqual(sorted(declared), mapped["whatsapp"])

    def test_voice_providers_match_node_declaration(self):
        declared = _declared_providers(VoiceConfig)
        self.assertIn("bolna", declared)
        mapped = channel_taxonomy.channel_provider_map()
        self.assertIn("voice", mapped)
        self.assertEqual(sorted(declared), mapped["voice"])


class ChannelProviderMapSelfPopulatesTest(unittest.TestCase):
    def test_map_populates_in_a_fresh_interpreter_without_node_imports(self):
        """channel_taxonomy alone must populate NODE_REGISTRY — not depend on import order."""
        import subprocess
        import sys

        script = (
            "from app.services.orchestration import channel_taxonomy as ct;"
            "print(ct.channel_provider_map());"
            "print(ct.resolve_channel('wa'))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "backend"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(
            ast.literal_eval(lines[0]),
            {"whatsapp": ["aisensy", "wati"], "voice": ["bolna"]},
        )
        self.assertEqual(lines[1], "whatsapp")


class ResolveChannelTest(unittest.TestCase):
    def test_alias_wa_resolves_to_whatsapp(self):
        self.assertEqual(channel_taxonomy.resolve_channel("wa"), "whatsapp")

    def test_alias_phone_call_resolves_to_voice(self):
        self.assertEqual(channel_taxonomy.resolve_channel("phone call"), "voice")

    def test_unknown_text_resolves_to_none(self):
        self.assertIsNone(channel_taxonomy.resolve_channel("nonsense"))


if __name__ == "__main__":
    unittest.main()
