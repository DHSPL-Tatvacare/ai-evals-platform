import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.evaluator import Evaluator
from app.models.mixins.shareable import Visibility
from app.services.evaluator_seed_catalog import (
    VOICE_RX_API_VARIANT,
    collapse_visible_seeded_evaluators,
    get_seed_specs,
    is_canonical_seeded_default,
    match_seed_spec,
    resolve_seed_variant,
)


def _make_evaluator(
    *,
    tenant_id,
    user_id,
    app_id: str,
    name: str,
    prompt: str,
    output_schema: list,
    visibility: Visibility = Visibility.SHARED,
    listing_id=None,
    seed_key: str | None = None,
    seed_variant: str | None = None,
    forked_from=None,
):
    return Evaluator(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        app_id=app_id,
        name=name,
        prompt=prompt,
        output_schema=output_schema,
        visibility=visibility,
        listing_id=listing_id,
        seed_key=seed_key,
        seed_variant=seed_variant,
        forked_from=forked_from,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_resolve_seed_variant_for_voice_rx_source_types():
    assert resolve_seed_variant('voice-rx', 'upload') == 'upload'
    assert resolve_seed_variant('voice-rx', 'api') == 'api'
    assert resolve_seed_variant('voice-rx', 'other') is None
    assert resolve_seed_variant('kaira-bot', 'upload') is None


def test_match_seed_spec_uses_variant_to_disambiguate_voice_rx_defaults():
    api_spec = get_seed_specs('voice-rx', seed_variant=VOICE_RX_API_VARIANT)[0]

    matched = match_seed_spec(
        app_id='voice-rx',
        seed_variant='api',
        name=api_spec.name,
        prompt=api_spec.prompt,
        output_schema=api_spec.output_schema,
    )

    assert matched is not None
    assert matched.seed_key == api_spec.seed_key
    assert matched.seed_variant == 'api'


def test_collapse_visible_seeded_evaluators_prefers_tenant_default_over_system_row():
    tenant_id = uuid.uuid4()
    spec = get_seed_specs('kaira-bot')[0]
    system_seed = _make_evaluator(
        tenant_id=SYSTEM_TENANT_ID,
        user_id=SYSTEM_USER_ID,
        app_id='kaira-bot',
        name=spec.name,
        prompt=spec.prompt,
        output_schema=spec.output_schema,
        seed_key=spec.seed_key,
    )
    tenant_seed = _make_evaluator(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        app_id='kaira-bot',
        name=spec.name,
        prompt=spec.prompt,
        output_schema=spec.output_schema,
        seed_key=spec.seed_key,
    )

    visible = collapse_visible_seeded_evaluators([system_seed, tenant_seed], listing_id=None)

    assert visible == [tenant_seed]
    assert is_canonical_seeded_default(tenant_seed) is True


def test_collapse_visible_seeded_evaluators_hides_legacy_listing_clone_when_canonical_exists():
    tenant_id = uuid.uuid4()
    spec = get_seed_specs('voice-rx', seed_variant='upload')[0]
    listing_id = uuid.uuid4()
    canonical_seed = _make_evaluator(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        app_id='voice-rx',
        name=spec.name,
        prompt=spec.prompt,
        output_schema=spec.output_schema,
        seed_key=spec.seed_key,
        seed_variant='upload',
    )
    legacy_clone = _make_evaluator(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        app_id='voice-rx',
        name=spec.name,
        prompt=spec.prompt,
        output_schema=spec.output_schema,
        visibility=Visibility.PRIVATE,
        listing_id=listing_id,
        seed_key=spec.seed_key,
        seed_variant='upload',
    )

    visible = collapse_visible_seeded_evaluators(
        [legacy_clone, canonical_seed],
        listing_id=listing_id,
    )

    assert visible == [canonical_seed]
