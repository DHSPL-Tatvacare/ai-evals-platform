# 03 — Backend `_build_summary` Additions

## Files involved

| File | Action |
|---|---|
| `backend/app/services/evaluators/voice_rx_runner.py` | Add recall/precision to summary |

---

## 1. Current `_build_summary` for API flow

Located at `voice_rx_runner.py:939-960`:

```python
else:
    # API: count from fieldCritiques
    field_critiques = critique.get("fieldCritiques", [])
    total = len(field_critiques)
    if total > 0:
        matches = sum(1 for fc in field_critiques if fc.get("match", False))
        summary["overall_accuracy"] = matches / total
        summary["total_items"] = total
        severity_dist = _count_severity(field_critiques, key="severity")
        summary["severity_distribution"] = severity_dist
        summary["critical_errors"] = severity_dist.get("CRITICAL", 0)
        summary["moderate_errors"] = severity_dist.get("MODERATE", 0)
        summary["minor_errors"] = severity_dist.get("MINOR", 0)
```

Currently computes:
- `overall_accuracy` = match count / total (same as frontend "Field Accuracy")
- `total_items` = total field critiques
- `severity_distribution`, `critical_errors`, `moderate_errors`, `minor_errors`

Missing: recall and precision.

---

## 2. Proposed additions

After the existing `summary["overall_accuracy"]` block, add recall and precision:

```python
else:
    # API: count from fieldCritiques
    field_critiques = critique.get("fieldCritiques", [])
    total = len(field_critiques)
    if total > 0:
        matches = sum(1 for fc in field_critiques if fc.get("match", False))
        summary["overall_accuracy"] = matches / total
        summary["total_items"] = total

        # Extraction Recall: how many items did the API capture?
        # api_only and matched items have real apiValue; judge_only have "(not found)"
        api_extracted = sum(
            1 for fc in field_critiques
            if str(fc.get("apiValue", "(not found)")) != "(not found)"
        )
        summary["extraction_recall"] = api_extracted / total if total > 0 else 0
        summary["api_extracted_count"] = api_extracted

        # Extraction Precision: of what the API extracted, how many were correct?
        api_correct = sum(
            1 for fc in field_critiques
            if str(fc.get("apiValue", "(not found)")) != "(not found)"
            and fc.get("match", False)
        )
        summary["extraction_precision"] = (
            api_correct / api_extracted if api_extracted > 0 else 0
        )
        summary["api_correct_count"] = api_correct

        severity_dist = _count_severity(field_critiques, key="severity")
        summary["severity_distribution"] = severity_dist
        summary["critical_errors"] = severity_dist.get("CRITICAL", 0)
        summary["moderate_errors"] = severity_dist.get("MODERATE", 0)
        summary["minor_errors"] = severity_dist.get("MINOR", 0)
```

---

## 3. Resulting summary shape for API flow

```json
{
  "flow_type": "api",
  "overall_accuracy": 0.29,
  "total_items": 31,
  "extraction_recall": 0.71,
  "api_extracted_count": 22,
  "extraction_precision": 0.409,
  "api_correct_count": 9,
  "severity_distribution": {
    "CRITICAL": 5,
    "MODERATE": 10,
    "MINOR": 7
  },
  "critical_errors": 5,
  "moderate_errors": 10,
  "minor_errors": 7
}
```

This summary is stored in `eval_runs.summary` (JSONB) and used by:
- Dashboard listing table (shows overall_accuracy as the quality indicator)
- Runs list view (shows summary stats)

The new fields (`extraction_recall`, `extraction_precision`, `api_extracted_count`, `api_correct_count`) are additive — no existing consumers will break.

---

## 4. Frontend metrics vs backend summary

The frontend `computeApiFlowMetrics()` (from `01_TYPES_AND_COMPUTATION.md`) computes the same values independently from the stored `fieldCritiques`. The backend summary is a pre-computed snapshot stored at eval completion time.

Both use the same formulas:

| Metric | Frontend formula | Backend formula |
|---|---|---|
| Field Accuracy | `matchCount / total * 100` | `matches / total` (stored as 0-1 ratio) |
| Recall | `apiExtracted / total * 100` | `api_extracted / total` (stored as 0-1 ratio) |
| Precision | `apiCorrect / apiExtracted * 100` | `api_correct / api_extracted` (stored as 0-1 ratio) |

The frontend displays as percentages (29.0%), the backend stores as ratios (0.29). The frontend computation is the source of truth for the MetricsBar display; the backend summary is for dashboard/listing views where recomputing per-listing would be expensive.

---

## 5. No schema changes needed

`eval_runs.summary` is a JSONB column — no migration required. The new keys are just additional fields in the JSON object. Existing summaries (upload flow) already have a different shape and are not affected.

---

## 6. Priority

This backend change is **optional/low-priority** for the initial fix. The frontend metrics fix (files 01 and 02) solves the immediate bug (MetricsBar showing wrong values). The backend summary enhancement is useful for:
- Dashboard views that show metrics without loading full fieldCritiques
- Future export/reporting features
- API consumers of the eval_runs endpoint

It can be shipped alongside the frontend fix or deferred.
