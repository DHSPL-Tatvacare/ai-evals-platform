"""Builds the palette descriptor list — fed to the frontend builder.

The label/description map is maintained inline so a new node only needs an
entry alongside its handler module.
"""
from __future__ import annotations

from typing import Optional

from app.schemas.orchestration import NodeTypeDescriptor
from app.services.orchestration.node_registry import NODE_REGISTRY


_LABELS: dict[str, tuple[str, str]] = {
    "source.cohort_query":   ("Cohort Query (SQL)",     "Materialize entry cohort from a source table."),
    "source.event_trigger":  ("Event Trigger",          "Entry from an external event (webhook, sync)."),
    "filter.eligibility":    ("Eligibility",            "Predicate filter — passed / skipped."),
    "filter.consent_gate":   ("Consent Gate",           "Drops opted-out recipients."),
    "logic.conditional":     ("Conditional",            "Branch on a payload predicate (true / false)."),
    "logic.split":           ("Split",                  "N-way split by field value or random %."),
    "logic.wait":            ("Wait",                   "Pause for a duration or until a datetime."),
    "logic.merge":           ("Merge",                  "Union multiple input edges (with optional dedupe)."),
    "core.webhook_out":      ("Webhook Out",            "POST a JSON body to an external URL."),
    "sink.complete":         ("Complete",               "Terminal — marks recipient completed."),
    "crm.send_wati":         ("Send WhatsApp (WATI)",   "Sends a WATI template per recipient."),
    "crm.place_bolna_call":  ("Place AI Call (Bolna)",  "Places an outbound AI voice call."),
    "crm.send_sms":          ("Send SMS",               "Sends an SMS via configured provider."),
    "crm.lsq_update_stage":  ("LSQ Update Stage",       "Sets ProspectStage on each recipient."),
    "crm.lsq_log_activity":  ("LSQ Log Activity",       "Logs ProspectActivity on each recipient."),
    "clinical.schedule_lab":          ("Schedule Lab",       "Queue lab order to EMR via clinical action outbox."),
    "clinical.assign_care_team_task": ("Assign Care Team",   "Queue task to care manager / physician / etc."),
    "clinical.send_pro_assessment":   ("Send PRO",           "Send PHQ-9 / DDS / MMAS link to patient."),
    "clinical.emr_write":             ("EMR Write",          "Write structured note / observation to EMR."),
    "clinical.escalation_uptier":     ("Escalation",         "Escalate to physician / specialist with urgency."),
}


def list_node_types(workflow_type: Optional[str] = None) -> list[NodeTypeDescriptor]:
    out: list[NodeTypeDescriptor] = []
    for (wf_match, node_type), handler in NODE_REGISTRY.items():
        if node_type.startswith("test."):
            continue
        if workflow_type and wf_match not in (workflow_type, "*"):
            continue
        label, description = _LABELS.get(node_type, (node_type, ""))
        out.append(NodeTypeDescriptor(
            node_type=node_type,
            workflow_type=wf_match,
            category=handler.category,
            label=label,
            description=description,
            output_edges=list(handler.output_edges),
            config_schema=handler.config_schema.model_json_schema(),
        ))
    return sorted(out, key=lambda n: (n.category, n.node_type))
