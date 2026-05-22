"""Phase 0 — EventSourceAdapter protocol, CanonicalEventBatch shape, catalog + alignment guard."""
from __future__ import annotations

import pytest


def test_canonical_event_batch_shape():
    from app.services.orchestration.adapters.canonical import (
        CanonicalEventBatch,
        CanonicalEventRecipient,
    )

    batch = CanonicalEventBatch(
        event_name="crm.lead.created",
        ingest_id="frappe|Lead|LEAD-1|after_insert",
        recipients=[
            CanonicalEventRecipient(recipient_id="LEAD-1", payload={"name": "A"}),
        ],
    )
    assert batch.event_name == "crm.lead.created"
    assert batch.ingest_id == "frappe|Lead|LEAD-1|after_insert"
    assert batch.recipients[0].recipient_id == "LEAD-1"
    assert batch.recipients[0].payload == {"name": "A"}


def test_canonical_event_recipient_defaults_payload():
    from app.services.orchestration.adapters.canonical import CanonicalEventRecipient

    r = CanonicalEventRecipient(recipient_id="X")
    assert r.payload == {}


def test_event_source_adapter_protocol_importable():
    from app.services.orchestration.adapters.protocol import EventSourceAdapter

    # Protocol carries the three required methods.
    assert hasattr(EventSourceAdapter, "map_event_name")
    assert hasattr(EventSourceAdapter, "normalize_event")
    assert hasattr(EventSourceAdapter, "verify_signature")


def test_catalog_keyed_lowercase_workflow_type():
    from app.services.orchestration.event_catalog import catalog_for_workflow_type

    crm = catalog_for_workflow_type("crm")
    clinical = catalog_for_workflow_type("clinical")
    assert "crm.lead.created" in crm
    assert "clinical.program.enrolled" in clinical
    # Uppercase is a silent empty (load-bearing) — not an error.
    assert catalog_for_workflow_type("CRM") == []
    assert catalog_for_workflow_type("CLINICAL") == []


def test_catalog_namespaced_by_workflow_type():
    from app.services.orchestration.event_catalog import catalog_for_workflow_type

    for name in catalog_for_workflow_type("crm"):
        assert name.startswith("crm.")
    for name in catalog_for_workflow_type("clinical"):
        assert name.startswith("clinical.")


def test_clinical_catalog_seeds_confirmed_and_proposed():
    from app.services.orchestration.event_catalog import catalog_for_workflow_type

    clinical = set(catalog_for_workflow_type("clinical"))
    confirmed = {
        "clinical.program.enrolled", "clinical.diagnostic.landing",
        "clinical.diagnostic.intent", "clinical.diagnostic.details_submitted",
        "clinical.diagnostic.address_submitted", "clinical.diagnostic.slot_selected",
        "clinical.diagnostic.booking_confirmed", "clinical.labtest.booked",
        "clinical.appointment.booked", "clinical.drug.claimed",
        "clinical.order.punched", "clinical.assessment.completed",
        "clinical.score.logged", "clinical.plan.purchased",
    }
    proposed = {
        "clinical.refill.due", "clinical.dose.missed",
        "clinical.adherence.check_due", "clinical.vital.submitted",
    }
    assert confirmed <= clinical
    assert proposed <= clinical


def test_alignment_guard_every_adapter_event_map_subset_of_catalog():
    """Every registered event_source adapter's EVENT_MAP values must be in the
    catalog for the adapter's workflow_type — mirrors the manifest validator."""
    from app.services.orchestration.event_catalog import (
        assert_adapters_aligned_with_catalog,
    )

    # Raises on drift; no-op when aligned. Importing the adapters package
    # registers every vendor adapter as a side effect.
    import app.services.orchestration.adapters  # noqa: F401

    assert_adapters_aligned_with_catalog()
