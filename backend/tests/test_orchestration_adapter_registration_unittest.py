"""Vendor adapters must self-register on package import in every entrypoint."""
from __future__ import annotations


def test_adapters_self_register_on_package_import():
    # Importing the adapters package alone must populate the registry — the
    # worker process relies on this (it never ran the backend lifespan that
    # used to import the vendor modules explicitly).
    from app.services.orchestration.adapters import registered_adapters

    regs = set(registered_adapters())
    assert ("messaging", "wati") in regs
    assert ("voice", "bolna") in regs
    assert ("messaging", "aisensy") in regs


def test_registry_resolves_messaging_wati():
    from app.services.orchestration.adapters import resolve_adapter

    adapter = resolve_adapter(capability="messaging", vendor="wati")
    assert adapter is not None
