# Orchestration Workflow JSON Contract

Single source of truth for the **export / import / Claude-authored** JSON
shape consumed by the orchestration builder.

This file is **auto-generated** by
`backend/scripts/dump_workflow_contract.py`. Do not hand-edit. To refresh:

```bash
PYTHONPATH=backend python -m scripts.dump_workflow_contract
```

**Audience:** paste this file into Claude **along with the relevant app
manifest YAML(s)** from `backend/app/services/chat_engine/manifests/` when
asking it to generate a workflow as JSON. The manifest tells Claude what
data is available; this contract tells Claude how to wire it into nodes.

**Compatibility guarantee:** every Pydantic `_Config` model below ships
with `extra='forbid'`. Fabricating a field that isn't in the schema will
fail validation — silently dropping unknown keys is the bug class we
explicitly fixed (see `CLAUDE.md` invariants).

## 1. Envelope schema (export / import JSON)

The export bundle is a JSON object with this top-level shape:

```jsonc
{
  "schema_version": 1,                 // bump only if the envelope shape changes
  "workflow": {
    "name": "MQL Concierge — Aug 2026",
    "description": "optional",
    "app_id": "inside-sales",          // platform.applications.id
    "workflow_type": "crm",            // "crm" | "clinical"
    "visibility": "private"            // "private" | "shared"
  },
  "definition": { /* WorkflowDefinition — see below */ },
  "triggers": [                        // optional; omit for manual-only
    {
      "kind": "cron",                  // "cron" | "event" | "manual"
      "cron_expression": "0 10 * * 1-5",
      "event_name": null,
      "params": {},
      "active": true
    }
  ],
  "layout": {                          // optional, but recommended for round-trip
    "viewport": { "x": 0, "y": 0, "zoom": 1 }
    // node positions are carried inside definition.nodes[].position
  }
}
```

`definition` is the canonical workflow definition stored on
`orchestration.workflow_versions.definition`. Its JSON Schema follows.

### `WorkflowDefinition` (JSON Schema)
```json
{
  "description": "The JSONB shape stored in workflow_versions.definition.\n\nKept permissive at the boundary (raw ``dict`` lists) because the\nPhase 11 normalization layer is the single place that reshapes legacy\npersisted definitions. Strict validation lives in\n``definition_validator.validate_definition`` and runs at publish time.",
  "properties": {
    "nodes": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Nodes",
      "type": "array"
    },
    "edges": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Edges",
      "type": "array"
    },
    "canvas": {
      "additionalProperties": true,
      "title": "Canvas",
      "type": "object"
    }
  },
  "title": "WorkflowDefinition",
  "type": "object"
}
```

## 2. Validate endpoint

`POST /api/orchestration/workflows/validate`

Pure validate — runs the same pipeline as publish (`normalize_definition`
→ `validate_dispatch_required_fields` → `validate_definition`) without
writing to the database. Used by the JSON import preview and by
Claude-generated-payload checks.

- **Auth:** Bearer token + `orchestration:manage` permission. App-gated
  against `app_id` (must be in `auth.app_access`).
- **HTTP status:** always `200` when the request body itself parses.
  Validation outcomes land in the response body — `ok=false` means do
  not import; `errors[]` carries the same `{node_id, field, message}`
  shape `PublishErrorPanel` already renders.
- **Connection IDs:** unknown `connection_id` refs come back as
  `warnings[]`, not `errors[]`. The runtime contract still enforces the
  binding at publish, but the import can land as a draft the user
  rebinds in the builder.

### Request body — `WorkflowValidateRequest`
```json
{
  "$defs": {
    "WorkflowDefinition": {
      "description": "The JSONB shape stored in workflow_versions.definition.\n\nKept permissive at the boundary (raw ``dict`` lists) because the\nPhase 11 normalization layer is the single place that reshapes legacy\npersisted definitions. Strict validation lives in\n``definition_validator.validate_definition`` and runs at publish time.",
      "properties": {
        "nodes": {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "title": "Nodes",
          "type": "array"
        },
        "edges": {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "title": "Edges",
          "type": "array"
        },
        "canvas": {
          "additionalProperties": true,
          "title": "Canvas",
          "type": "object"
        }
      },
      "title": "WorkflowDefinition",
      "type": "object"
    }
  },
  "description": "Body for ``POST /api/orchestration/workflows/validate``.\n\nUsed by the import-JSON preview and by Claude-generated workflow JSON.\nPure: no DB writes, no workflow row created. ``workflow_type`` and\n``app_id`` are required because the validator's node-registry lookup is\nnamespaced by workflow type and the connection-id warning check is\nscoped by tenant + app.",
  "properties": {
    "appId": {
      "title": "Appid",
      "type": "string"
    },
    "workflowType": {
      "enum": [
        "crm",
        "clinical"
      ],
      "title": "Workflowtype",
      "type": "string"
    },
    "definition": {
      "$ref": "#/$defs/WorkflowDefinition"
    }
  },
  "required": [
    "appId",
    "workflowType",
    "definition"
  ],
  "title": "WorkflowValidateRequest",
  "type": "object"
}
```

### Response body — `WorkflowValidateResponse`
```json
{
  "$defs": {
    "WorkflowValidateIssue": {
      "description": "One error or warning row in the validate response.\n\nShape matches what ``PublishErrorPanel`` already renders so the import\npreview can reuse the same component.",
      "properties": {
        "nodeId": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Nodeid"
        },
        "field": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Field"
        },
        "message": {
          "title": "Message",
          "type": "string"
        }
      },
      "required": [
        "message"
      ],
      "title": "WorkflowValidateIssue",
      "type": "object"
    }
  },
  "properties": {
    "ok": {
      "title": "Ok",
      "type": "boolean"
    },
    "errors": {
      "items": {
        "$ref": "#/$defs/WorkflowValidateIssue"
      },
      "title": "Errors",
      "type": "array"
    },
    "warnings": {
      "items": {
        "$ref": "#/$defs/WorkflowValidateIssue"
      },
      "title": "Warnings",
      "type": "array"
    },
    "normalizedDefinition": {
      "additionalProperties": true,
      "title": "Normalizeddefinition",
      "type": "object"
    }
  },
  "required": [
    "ok",
    "normalizedDefinition"
  ],
  "title": "WorkflowValidateResponse",
  "type": "object"
}
```

## 3. Node registry

20 node types live in the registry. Resolution is by `(workflow_type,
node_type)` with a `*` fallback for nodes shared across workflow types.
| node_type | category | workflow_type | config class |
|-----------|----------|---------------|--------------|
| `source.cohort_query` | source | shared (`*`) | `app.services.orchestration.nodes._cohort_query_compiler.CohortQueryConfig` |
| `source.event_trigger` | source | shared (`*`) | `app.services.orchestration.nodes.source_event_trigger._Config` |
| `filter.consent_gate` | filter | shared (`*`) | `app.services.orchestration.nodes.filter_consent_gate._Config` |
| `filter.eligibility` | filter | shared (`*`) | `app.services.orchestration.nodes.filter_eligibility._Config` |
| `logic.conditional` | logic | shared (`*`) | `app.services.orchestration.nodes.logic_conditional._Config` |
| `logic.merge` | logic | shared (`*`) | `app.services.orchestration.nodes.logic_merge._Config` |
| `logic.split` | logic | shared (`*`) | `app.services.orchestration.nodes.logic_split._Config` |
| `logic.wait` | logic | shared (`*`) | `app.services.orchestration.nodes.logic_wait._Config` |
| `core.webhook_out` | action | shared (`*`) | `app.services.orchestration.nodes.core_webhook_out._Config` |
| `clinical.assign_care_team_task` | action | `clinical` | `app.services.orchestration.nodes.clinical_assign_care_team_task._Config` |
| `clinical.emr_write` | action | `clinical` | `app.services.orchestration.nodes.clinical_emr_write._Config` |
| `clinical.schedule_lab` | action | `clinical` | `app.services.orchestration.nodes.clinical_schedule_lab._Config` |
| `clinical.send_pro_assessment` | action | `clinical` | `app.services.orchestration.nodes.clinical_send_pro_assessment._Config` |
| `crm.lsq_log_activity` | action | `crm` | `app.services.orchestration.nodes.crm_lsq_log_activity._Config` |
| `crm.lsq_update_stage` | action | `crm` | `app.services.orchestration.nodes.crm_lsq_update_stage._Config` |
| `crm.place_bolna_call` | action | `crm` | `app.services.orchestration.nodes.crm_place_bolna_call._Config` |
| `crm.send_sms` | action | `crm` | `app.services.orchestration.nodes.crm_send_sms._Config` |
| `crm.send_wati` | action | `crm` | `app.services.orchestration.nodes.crm_send_wati._Config` |
| `clinical.escalation_uptier` | escalation | `clinical` | `app.services.orchestration.nodes.clinical_escalation_uptier._Config` |
| `sink.complete` | sink | shared (`*`) | `app.services.orchestration.nodes.sink_complete._Config` |

## 4. Per-node config schemas

Each `_Config` schema below is dumped via `BaseModel.model_json_schema()`
and is the **authoritative** contract for that node's `config` object.
Notes:

- `extra='forbid'` is universal. Unknown keys hard-fail validation.
- `required` fields are enforced at **publish**. Drafts tolerate missing
  required fields except for the dispatch fields gated by
  `validate_dispatch_required_fields` (Bolna `connection_id` / `agent_id`,
  WATI `connection_id` / `template_name` / `channel_number` /
  `broadcast_name`).
- Predicate / condition fields use the predicate AST defined in
  `backend/app/services/orchestration/predicate_contract.py`.

### `source.cohort_query` (source, scope: `shared`)
```json
{
  "$defs": {
    "CohortQueryFilter": {
      "additionalProperties": false,
      "properties": {
        "column": {
          "title": "Column",
          "type": "string"
        },
        "op": {
          "title": "Op",
          "type": "string"
        },
        "value": {
          "title": "Value"
        }
      },
      "required": [
        "column",
        "op",
        "value"
      ],
      "title": "CohortQueryFilter",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "Canonical Phase 11 cohort-query config.\n\nEither ``source_ref`` (preferred) or the legacy\n``source_table`` + ``id_column`` pair must be provided. When both are\ngiven, ``source_ref`` wins and the legacy fields are ignored.",
  "properties": {
    "source_ref": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Source Ref"
    },
    "payload_fields": {
      "items": {
        "type": "string"
      },
      "title": "Payload Fields",
      "type": "array"
    },
    "source_table": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Source Table"
    },
    "id_column": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Id Column"
    },
    "payload_columns": {
      "items": {
        "type": "string"
      },
      "title": "Payload Columns",
      "type": "array"
    },
    "filters": {
      "items": {
        "$ref": "#/$defs/CohortQueryFilter"
      },
      "title": "Filters",
      "type": "array"
    },
    "lookback_hours": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Lookback Hours"
    },
    "lookback_column": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Lookback Column"
    },
    "consent_gate_channel": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Consent Gate Channel"
    },
    "next_node_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Next Node Id"
    }
  },
  "title": "CohortQueryConfig",
  "type": "object"
}
```

### `source.event_trigger` (source, scope: `shared`)
```json
{
  "additionalProperties": false,
  "description": "Phase 11 contract: empty in canonical form. The legacy ``next_node_id``\nfield is kept as Optional so unit tests and pre-Phase-11 saved\ndefinitions still load \u2014 the normalizer drops it from canonical\ndefinitions and the executor prefers the graph-derived target.",
  "properties": {
    "next_node_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Next Node Id"
    }
  },
  "title": "_Config",
  "type": "object"
}
```

### `filter.consent_gate` (filter, scope: `shared`)
```json
{
  "additionalProperties": false,
  "properties": {
    "channel": {
      "enum": [
        "wa",
        "voice",
        "sms",
        "email"
      ],
      "title": "Channel",
      "type": "string"
    },
    "consent_policy": {
      "default": "permissive",
      "enum": [
        "permissive",
        "explicit_optin"
      ],
      "title": "Consent Policy",
      "type": "string"
    }
  },
  "required": [
    "channel"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `filter.eligibility` (filter, scope: `shared`)
```json
{
  "additionalProperties": false,
  "properties": {
    "predicate": {
      "additionalProperties": true,
      "title": "Predicate",
      "type": "object"
    }
  },
  "required": [
    "predicate"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `logic.conditional` (logic, scope: `shared`)
```json
{
  "additionalProperties": false,
  "properties": {
    "predicate": {
      "additionalProperties": true,
      "title": "Predicate",
      "type": "object"
    }
  },
  "required": [
    "predicate"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `logic.merge` (logic, scope: `shared`)
```json
{
  "additionalProperties": false,
  "properties": {
    "merge_policy": {
      "default": "dedupe",
      "enum": [
        "dedupe",
        "first_wins",
        "last_wins"
      ],
      "title": "Merge Policy",
      "type": "string"
    },
    "payload_policy": {
      "default": "last_wins",
      "enum": [
        "first_wins",
        "last_wins",
        "shallow_merge"
      ],
      "title": "Payload Policy",
      "type": "string"
    }
  },
  "title": "_Config",
  "type": "object"
}
```

### `logic.split` (logic, scope: `shared`)
```json
{
  "$defs": {
    "_Branch": {
      "additionalProperties": false,
      "properties": {
        "id": {
          "title": "Id",
          "type": "string"
        },
        "label": {
          "title": "Label",
          "type": "string"
        },
        "match": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Match"
        },
        "weight": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Weight"
        }
      },
      "required": [
        "id",
        "label"
      ],
      "title": "_Branch",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "mode": {
      "enum": [
        "by_field",
        "random"
      ],
      "title": "Mode",
      "type": "string"
    },
    "field": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Field"
    },
    "branches": {
      "items": {
        "$ref": "#/$defs/_Branch"
      },
      "minItems": 2,
      "title": "Branches",
      "type": "array"
    },
    "default_branch_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Default Branch Id"
    },
    "drop_unmatched": {
      "default": false,
      "title": "Drop Unmatched",
      "type": "boolean"
    }
  },
  "required": [
    "mode",
    "branches"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `logic.wait` (logic, scope: `shared`)
```json
{
  "$defs": {
    "_EventCorrelation": {
      "additionalProperties": false,
      "description": "How an inbound event row identifies the parked recipient.\n\n``recipient_id_field`` is the JSON path inside the event payload whose\nvalue matches a parked recipient's ``recipient_id``. Future commits will\nextend this with provider-specific correlation (e.g. ``wati_message_id``\n-> action row -> recipient).",
      "properties": {
        "recipient_id_field": {
          "title": "Recipient Id Field",
          "type": "string"
        }
      },
      "required": [
        "recipient_id_field"
      ],
      "title": "_EventCorrelation",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "Flat union \u2014 only the fields valid for the chosen ``mode`` are required.\n\nThe ``model_validator`` below enforces shape per mode so authoring tools\nsurface clear errors instead of relying on per-mode subclasses.",
  "properties": {
    "mode": {
      "default": "duration",
      "enum": [
        "duration",
        "until_datetime",
        "event",
        "event_or_timeout"
      ],
      "title": "Mode",
      "type": "string"
    },
    "duration_hours": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Duration Hours"
    },
    "until_datetime": {
      "anyOf": [
        {
          "format": "date-time",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Until Datetime"
    },
    "event_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Event Name"
    },
    "correlation": {
      "anyOf": [
        {
          "$ref": "#/$defs/_EventCorrelation"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "event_match": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Event Match"
    },
    "timeout_hours": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Timeout Hours"
    }
  },
  "title": "_Config",
  "type": "object"
}
```

### `core.webhook_out` (action, scope: `shared`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "connection_id": {
      "anyOf": [
        {
          "format": "uuid",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Connection Id",
      "x-provider": "webhook",
      "x-type": "connection_picker"
    },
    "url": {
      "title": "Url",
      "type": "string"
    },
    "method": {
      "default": "POST",
      "enum": [
        "POST",
        "PUT"
      ],
      "title": "Method",
      "type": "string"
    },
    "headers": {
      "additionalProperties": {
        "type": "string"
      },
      "title": "Headers",
      "type": "object"
    },
    "body": {
      "title": "Body",
      "x-type": "structured_request_body"
    },
    "timeout_seconds": {
      "default": 10.0,
      "title": "Timeout Seconds",
      "type": "number"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "url"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `clinical.assign_care_team_task` (action, scope: `clinical`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "role": {
      "default": "care_manager",
      "enum": [
        "care_manager",
        "physician",
        "pharmacist",
        "nutritionist"
      ],
      "title": "Role",
      "type": "string"
    },
    "task_label": {
      "title": "Task Label",
      "type": "string"
    },
    "cadence": {
      "default": "once",
      "enum": [
        "once",
        "weekly",
        "monthly"
      ],
      "title": "Cadence",
      "type": "string"
    },
    "sla_hours": {
      "default": 24,
      "title": "Sla Hours",
      "type": "integer"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "task_label"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `clinical.emr_write` (action, scope: `clinical`)
```json
{
  "additionalProperties": false,
  "properties": {
    "note_type": {
      "default": "progress_note",
      "enum": [
        "progress_note",
        "observation",
        "encounter",
        "care_plan_update"
      ],
      "title": "Note Type",
      "type": "string"
    },
    "template": {
      "description": "Note body; supports {{var}} from payload.",
      "title": "Template",
      "type": "string"
    },
    "structured_fields": {
      "additionalProperties": true,
      "title": "Structured Fields",
      "type": "object"
    }
  },
  "required": [
    "template"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `clinical.schedule_lab` (action, scope: `clinical`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "test_code": {
      "description": "Lab test code (LOINC or local).",
      "title": "Test Code",
      "type": "string"
    },
    "test_name": {
      "title": "Test Name",
      "type": "string"
    },
    "frequency": {
      "default": "once",
      "enum": [
        "once",
        "monthly",
        "quarterly",
        "biannual",
        "annual"
      ],
      "title": "Frequency",
      "type": "string"
    },
    "notify_roles": {
      "items": {
        "enum": [
          "care_manager",
          "physician",
          "pharmacist"
        ],
        "type": "string"
      },
      "title": "Notify Roles",
      "type": "array"
    },
    "urgency": {
      "default": "routine",
      "enum": [
        "routine",
        "urgent",
        "stat"
      ],
      "title": "Urgency",
      "type": "string"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "test_code",
    "test_name"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `clinical.send_pro_assessment` (action, scope: `clinical`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "instrument": {
      "default": "PHQ9",
      "enum": [
        "PHQ9",
        "DDS",
        "MMAS",
        "EQ5D",
        "PROMIS"
      ],
      "title": "Instrument",
      "type": "string"
    },
    "delivery_channel": {
      "default": "wa",
      "enum": [
        "sms",
        "email",
        "wa"
      ],
      "title": "Delivery Channel",
      "type": "string"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "title": "_Config",
  "type": "object"
}
```

### `crm.lsq_log_activity` (action, scope: `crm`)
```json
{
  "additionalProperties": false,
  "properties": {
    "connection_id": {
      "format": "uuid",
      "title": "Connection Id",
      "type": "string",
      "x-provider": "lsq",
      "x-type": "connection_picker"
    },
    "activity_event_code": {
      "title": "Activity Event Code",
      "type": "integer"
    },
    "note": {
      "title": "Note",
      "type": "string"
    },
    "fields": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Fields",
      "type": "array"
    }
  },
  "required": [
    "connection_id",
    "activity_event_code",
    "note"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `crm.lsq_update_stage` (action, scope: `crm`)
```json
{
  "additionalProperties": false,
  "properties": {
    "connection_id": {
      "format": "uuid",
      "title": "Connection Id",
      "type": "string",
      "x-provider": "lsq",
      "x-type": "connection_picker"
    },
    "target_stage": {
      "title": "Target Stage",
      "type": "string"
    }
  },
  "required": [
    "connection_id",
    "target_stage"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `crm.place_bolna_call` (action, scope: `crm`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "connection_id": {
      "format": "uuid",
      "title": "Connection Id",
      "type": "string",
      "x-provider": "bolna",
      "x-type": "connection_picker"
    },
    "template_slug": {
      "description": "Internal platform action template used for retry defaults, tracking, and idempotency. Stored as a slug behind this picker.",
      "title": "Action Template",
      "type": "string",
      "x-channel": "bolna",
      "x-type": "action_template_picker"
    },
    "agent_id": {
      "default": "",
      "description": "Pick the live Bolna agent placed on the call.",
      "title": "Bolna Agent",
      "type": "string",
      "x-type": "bolna_agent_picker"
    },
    "from_phone": {
      "default": "",
      "description": "Optional E.164 caller-id override. Leave blank to use the connection default or Bolna's per-agent default.",
      "title": "Caller ID Override",
      "type": "string"
    },
    "phone_field": {
      "default": "phone",
      "title": "Phone Field",
      "type": "string"
    },
    "variable_mappings": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Variable Mappings",
      "type": "array",
      "x-type": "variable_mapping_list"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "connection_id",
    "template_slug"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `crm.send_sms` (action, scope: `crm`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "connection_id": {
      "format": "uuid",
      "title": "Connection Id",
      "type": "string",
      "x-providers": [
        "msg91",
        "aisensy"
      ],
      "x-type": "connection_picker"
    },
    "template_slug": {
      "description": "Internal platform action template used for SMS body rendering, tracking, and idempotency. Stored as a slug behind this picker.",
      "title": "Action Template",
      "type": "string",
      "x-channel": "sms",
      "x-type": "action_template_picker"
    },
    "phone_field": {
      "default": "phone",
      "title": "Phone Field",
      "type": "string"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "connection_id",
    "template_slug"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `crm.send_wati` (action, scope: `crm`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "connection_id": {
      "format": "uuid",
      "title": "Connection Id",
      "type": "string",
      "x-provider": "wati",
      "x-type": "connection_picker"
    },
    "template_slug": {
      "description": "Internal platform action template used for dispatch policy, tracking, and idempotency. Stored as a slug behind this picker.",
      "title": "Action Template",
      "type": "string",
      "x-channel": "wati",
      "x-type": "action_template_picker"
    },
    "template_name": {
      "default": "",
      "description": "Pick the live WATI template the cohort receives.",
      "title": "WATI Template",
      "type": "string",
      "x-type": "wati_template_picker"
    },
    "channel_number": {
      "default": "",
      "description": "Pick the WhatsApp sender number this campaign goes from.",
      "title": "Channel Number",
      "type": "string",
      "x-type": "wati_channel_picker"
    },
    "broadcast_name": {
      "default": "",
      "description": "Campaign label sent to WATI as broadcast_name. Free-form text; tenants typically use a date-stamped slug like concierge_priority_2026_05.",
      "title": "Broadcast Name",
      "type": "string"
    },
    "phone_field": {
      "default": "whatsapp_number",
      "title": "Phone Field",
      "type": "string"
    },
    "variable_mappings": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Variable Mappings",
      "type": "array",
      "x-type": "variable_mapping_list"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "connection_id",
    "template_slug"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `clinical.escalation_uptier` (escalation, scope: `clinical`)
```json
{
  "$defs": {
    "AttemptPolicy": {
      "description": "Per-node attempt policy. Default = single attempt with no retry.",
      "properties": {
        "max_attempts": {
          "default": 1,
          "maximum": 10,
          "minimum": 1,
          "title": "Max Attempts",
          "type": "integer"
        },
        "backoff_kind": {
          "default": "immediate",
          "enum": [
            "immediate",
            "fixed_delay",
            "exponential"
          ],
          "title": "Backoff Kind",
          "type": "string"
        },
        "delay_minutes": {
          "default": 0,
          "maximum": 1440,
          "minimum": 0,
          "title": "Delay Minutes",
          "type": "integer"
        },
        "retry_on": {
          "items": {
            "type": "string"
          },
          "title": "Retry On",
          "type": "array"
        },
        "on_exhausted_output_id": {
          "default": "exhausted",
          "title": "On Exhausted Output Id",
          "type": "string"
        }
      },
      "title": "AttemptPolicy",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "target_role": {
      "default": "physician",
      "enum": [
        "physician",
        "specialist",
        "ed",
        "crisis_team"
      ],
      "title": "Target Role",
      "type": "string"
    },
    "urgency": {
      "default": "same_day",
      "enum": [
        "same_day",
        "48h",
        "next_review",
        "next_month"
      ],
      "title": "Urgency",
      "type": "string"
    },
    "reason": {
      "title": "Reason",
      "type": "string"
    },
    "attempt_policy": {
      "$ref": "#/$defs/AttemptPolicy",
      "x-type": "attempt_policy"
    }
  },
  "required": [
    "reason"
  ],
  "title": "_Config",
  "type": "object"
}
```

### `sink.complete` (sink, scope: `shared`)
```json
{
  "additionalProperties": false,
  "properties": {
    "reason": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Reason"
    }
  },
  "title": "_Config",
  "type": "object"
}
```

## 5. Worked examples

**Read this before copying.** Every example below has been validated
against the live `_Config` schemas in Section 4 and the output-edge
declarations in Section 3. If you change a node's config keys or output
ids, you MUST update the example. The fastest way to confirm a
hand-written workflow is correct: `POST /api/orchestration/workflows/validate`.

### 5.1 Minimal CRM workflow (one-hop Bolna call)

Notes:
- `source.event_trigger.config` does **not** carry the event name. The
  event is named on the **trigger row** at the workflow level (`triggers`
  array below).
- `crm.place_bolna_call` requires `connection_id` + `template_slug` at the
  Pydantic level, plus `agent_id` at the publish dispatch-gate. All three
  must be filled before publish; drafts may omit `agent_id`.
- The bolna node's outgoing edges use `output_id` values from
  `{"success", "exhausted"}` — never `"completed"` or `"default"`.

```json
{
  "schema_version": 1,
  "workflow": {
    "name": "Bolna ping demo",
    "description": "Single outbound voice call on MQL arrival.",
    "app_id": "inside-sales",
    "workflow_type": "crm",
    "visibility": "private"
  },
  "definition": {
    "nodes": [
      {
        "id": "src",
        "type": "source.event_trigger",
        "position": { "x": 0, "y": 0 },
        "data": { "label": "On MQL arrival" },
        "config": {}
      },
      {
        "id": "call",
        "type": "crm.place_bolna_call",
        "position": { "x": 320, "y": 0 },
        "data": { "label": "Place call" },
        "config": {
          "connection_id": "00000000-0000-0000-0000-000000000000",
          "template_slug": "mql_first_touch",
          "agent_id": "00000000-0000-0000-0000-000000000001",
          "phone_field": "phone"
        }
      },
      {
        "id": "done",
        "type": "sink.complete",
        "position": { "x": 640, "y": 0 },
        "data": { "label": "Done" },
        "config": {}
      }
    ],
    "edges": [
      { "id": "e1", "source": "src", "target": "call", "output_id": "default" },
      { "id": "e2", "source": "call", "target": "done", "output_id": "success" }
    ],
    "canvas": {}
  },
  "triggers": [
    { "kind": "event", "event_name": "lead.mql.arrived", "params": {}, "active": true }
  ]
}
```

### 5.2 Minimal clinical workflow (lab → care-team task)

Notes:
- `clinical.schedule_lab` requires both `test_code` and `test_name`. There
  is no `due_in_days` field — frequency is expressed via the `frequency`
  enum (see Section 4) or by re-firing the workflow on a schedule.
- `clinical.assign_care_team_task` requires `task_label`. There is no
  `task_type` or `due_in_days` field; cadence/SLA go on `cadence` /
  `sla_hours` (see Section 4).
- Clinical action outputs use `{"success", "exhausted"}`, never
  `"queued"`.

```json
{
  "schema_version": 1,
  "workflow": {
    "name": "DM2 routine labs",
    "description": "Order HbA1c on cohort entry and queue a follow-up task.",
    "app_id": "inside-sales",
    "workflow_type": "clinical",
    "visibility": "private"
  },
  "definition": {
    "nodes": [
      {
        "id": "src",
        "type": "source.cohort_query",
        "position": { "x": 0, "y": 0 },
        "data": { "label": "DM2 cohort" },
        "config": { "source_ref": "dm2_active_v1" }
      },
      {
        "id": "lab",
        "type": "clinical.schedule_lab",
        "position": { "x": 320, "y": 0 },
        "data": { "label": "Order HbA1c" },
        "config": { "test_code": "hba1c", "test_name": "HbA1c" }
      },
      {
        "id": "task",
        "type": "clinical.assign_care_team_task",
        "position": { "x": 640, "y": 0 },
        "data": { "label": "Follow up" },
        "config": { "task_label": "Review HbA1c result and call patient" }
      },
      {
        "id": "done",
        "type": "sink.complete",
        "position": { "x": 960, "y": 0 },
        "data": { "label": "Done" },
        "config": {}
      }
    ],
    "edges": [
      { "id": "e1", "source": "src", "target": "lab", "output_id": "default" },
      { "id": "e2", "source": "lab", "target": "task", "output_id": "success" },
      { "id": "e3", "source": "task", "target": "done", "output_id": "success" }
    ],
    "canvas": {}
  }
}
```


## 6. Output-edge index (every node, every output_id)

Auto-generated from each handler's declared `output_edges`. The
authoring agent must use **exactly** these strings as edge `output_id`
values — `validate_definition` rejects anything else.

`logic.split` is special: its branch ids are declared inline in
`config.branches[].id` rather than at the handler level. Edges out of a
split node use the branch's `id` as their `output_id`.

`logic.wait` declares all possible output ids but the validator only
accepts the subset matching the configured wait mode (see the wait
`_Config` schema in Section 4).
| node_type | output_ids |
|-----------|------------|
| `source.cohort_query` | `default` |
| `source.event_trigger` | `default` |
| `filter.consent_gate` | `allowed`, `blocked` |
| `filter.eligibility` | `passed`, `skipped` |
| `logic.conditional` | `true`, `false` |
| `logic.merge` | `default` |
| `logic.split` | _dynamic_ — declared in `config.branches[].id` |
| `logic.wait` | `wakeup`, `event`, `timeout` |
| `core.webhook_out` | `success`, `exhausted` |
| `clinical.assign_care_team_task` | `success`, `exhausted` |
| `clinical.emr_write` | `success`, `failed` |
| `clinical.schedule_lab` | `success`, `exhausted` |
| `clinical.send_pro_assessment` | `success`, `exhausted` |
| `crm.lsq_log_activity` | `success`, `failed` |
| `crm.lsq_update_stage` | `success`, `failed` |
| `crm.place_bolna_call` | `success`, `exhausted` |
| `crm.send_sms` | `success`, `exhausted` |
| `crm.send_wati` | `success`, `exhausted` |
| `clinical.escalation_uptier` | `success`, `exhausted` |
| `sink.complete` | _none (terminal)_ |
