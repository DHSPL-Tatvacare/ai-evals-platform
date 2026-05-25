"""Contract for the permission catalog — platform:manage cross-tenant surface."""


def test_platform_manage_is_registered_and_grantable():
    from app.auth.permission_catalog import PERMISSION_INDEX, VALID_PERMISSIONS
    assert "platform:manage" in VALID_PERMISSIONS
    entry = PERMISSION_INDEX["platform:manage"]
    assert entry.grantable is True
    assert entry.owner_only is False
    assert entry.group_id == "platform"


def test_platform_manage_appears_in_serialized_catalog():
    from app.auth.permission_catalog import serialize_permission_catalog
    out = serialize_permission_catalog()
    platform_group = next(
        (g for g in out["groups"] if g["id"] == "platform"), None
    )
    assert platform_group is not None
    ids = {p["id"] for p in platform_group["permissions"]}
    assert "platform:manage" in ids


def test_platform_bootstrap_still_owner_only():
    """platform:bootstrap is in OWNER_ONLY_SURFACES, not the grantable groups."""
    from app.auth.permission_catalog import PERMISSION_INDEX, serialize_permission_catalog
    assert "platform:bootstrap" not in PERMISSION_INDEX
    out = serialize_permission_catalog()
    owner_ids = {s["id"] for s in out["ownerOnlySurfaces"]}
    assert "platform:bootstrap" in owner_ids


def test_no_seeded_default_role_grants_platform_manage():
    """seed_defaults only auto-creates the Owner role per tenant; Owner has no
    enumerated permission list (it bypasses via ``AuthContext.is_owner``). No
    other default role grants ``platform:manage``. If a future seed adds canned
    roles, this test should grow to enumerate them and assert exclusion.
    """
    import re
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1]
        / "app" / "services" / "seed_defaults.py"
    ).read_text()
    # No literal permission-list mention of platform:manage anywhere in seed.
    assert not re.search(r"['\"]platform:manage['\"]", src), (
        "seed_defaults.py references 'platform:manage' — confirm no auto-grant added"
    )
