"""x-type → resolver-tool dispatch + exhaustiveness guard."""
from __future__ import annotations

import unittest


class FieldResolverDispatchTest(unittest.TestCase):
    def test_picker_xtypes_route_to_their_resolver_tool(self) -> None:
        from app.services.orchestration_authoring.field_resolver_dispatch import (
            resolver_for,
        )

        self.assertEqual(resolver_for('connection_picker'), 'resolve_connection')
        self.assertEqual(resolver_for('wati_template_picker'), 'resolve_template')
        self.assertEqual(resolver_for('recipient_field_picker'), 'list_cohort_fields')
        self.assertEqual(resolver_for('variable_mapping_list'), 'map_template_variables')

    def test_deliberately_unsupported_xtypes_are_explicit_not_absent(self) -> None:
        from app.services.orchestration_authoring.field_resolver_dispatch import (
            UNSUPPORTED,
            XTYPE_RESOLVER,
        )

        for x_type in (
            'bolna_agent_picker',
            'phone_number_picker',
            'wati_channel_picker',
            'structured_request_body',
        ):
            self.assertIn(x_type, XTYPE_RESOLVER, x_type)
            self.assertEqual(XTYPE_RESOLVER[x_type], UNSUPPORTED, x_type)

    def test_resolver_for_unknown_xtype_returns_unsupported(self) -> None:
        from app.services.orchestration_authoring.field_resolver_dispatch import (
            UNSUPPORTED,
            resolver_for,
        )

        self.assertEqual(resolver_for('not_a_real_picker'), UNSUPPORTED)

    def test_exhaustiveness_guard_every_declared_xtype_is_mapped(self) -> None:
        """A future picker field cannot be silently unhandled: every x-type
        actually declared in a node config schema MUST be a key in
        XTYPE_RESOLVER. Derived by scanning the registry, never hardcoded."""
        from app.services.orchestration_authoring.field_resolver_dispatch import (
            XTYPE_RESOLVER,
            declared_xtypes,
        )

        declared = declared_xtypes()
        self.assertTrue(declared, 'expected at least one declared x-type')
        missing = declared - set(XTYPE_RESOLVER)
        self.assertEqual(
            missing, set(),
            f'x-types declared in node schemas but unmapped: {sorted(missing)}',
        )


if __name__ == '__main__':
    unittest.main()
