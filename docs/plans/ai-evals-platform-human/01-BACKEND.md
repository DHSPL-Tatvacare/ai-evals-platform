# Phase 01 — Backend Endpoints

## New Endpoints (added to `backend/app/routes/eval_runs.py`)

### 1. PUT `/api/eval-runs/{ai_run_id}/human-review`

Upserts a human review linked to an AI evaluation run.

```python
@router.put("/api/eval-runs/{ai_run_id}/human-review")
async def upsert_human_review(
    ai_run_id: uuid.UUID,
    req: HumanReviewUpsert,
    db: AsyncSession = Depends(get_db),
):
```

**Logic**:
1. Fetch AI eval run by `ai_run_id` — 404 if not found
2. Validate AI run is `eval_type` in (`full_evaluation`, `custom`) — 400 otherwise
3. Query existing human review: `SELECT ... WHERE eval_type='human' AND listing_id=ai_run.listing_id AND config->>'aiEvalRunId' = str(ai_run_id)`
4. If exists → UPDATE result, summary, status, completed_at
5. If not → INSERT new EvalRun row:
   - `eval_type = 'human'`
   - `app_id = ai_run.app_id`
   - `listing_id = ai_run.listing_id`
   - `status = 'completed'`
   - `config = { 'aiEvalRunId': str(ai_run_id), 'reviewSchema': req.review_schema }`
   - `result = req.result`
   - `summary = req.summary`
   - `completed_at = utcnow()`
6. Return `_run_to_dict(human_run)`

**Request Body** (`HumanReviewUpsert`):
```python
class HumanReviewUpsert(CamelModel):
    review_schema: str  # 'segment_review' | 'field_review' | 'thread_review'
    result: dict        # { overallVerdict, notes?, items: [...] }
    summary: dict       # { totalItems, accepted, rejected, corrected, adjustedMetrics }
```

### 2. GET `/api/eval-runs/{ai_run_id}/human-review`

Fetches the human review linked to an AI eval run.

```python
@router.get("/api/eval-runs/{ai_run_id}/human-review")
async def get_human_review(
    ai_run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
```

**Logic**:
1. Query: `SELECT ... WHERE eval_type='human' AND config->>'aiEvalRunId' = str(ai_run_id) ORDER BY created_at DESC LIMIT 1`
2. If not found → return `null` (200, not 404 — absence is normal)
3. If found → return `_run_to_dict(human_run)`

**Why not a separate table**: The existing eval_runs table already supports `eval_type='human'` and JSONB columns for flexible storage. Adding a new table would duplicate the FK relationships, indexes, and serialization logic already built. The polymorphic eval_type pattern is established.

## Schema Addition (`backend/app/schemas/eval_run.py`)

```python
class HumanReviewUpsert(CamelModel):
    review_schema: str
    result: dict
    summary: dict
```

## JSONB Shapes

### config
```json
{
  "aiEvalRunId": "uuid-string",
  "reviewSchema": "segment_review"
}
```

### result (segment_review)
```json
{
  "overallVerdict": "accepted_with_corrections",
  "notes": "Optional reviewer notes",
  "items": [
    {
      "segmentIndex": 0,
      "verdict": "accept",
      "correctedText": null,
      "comment": null
    },
    {
      "segmentIndex": 3,
      "verdict": "correct",
      "correctedText": "Corrected text here",
      "comment": "Misheard medication name"
    },
    {
      "segmentIndex": 7,
      "verdict": "reject",
      "correctedText": null,
      "comment": "Completely wrong speaker attribution"
    }
  ]
}
```

### result (field_review)
```json
{
  "overallVerdict": "accepted",
  "notes": "",
  "items": [
    {
      "fieldPath": "rx.medications[0].dosage",
      "verdict": "accept",
      "correctedValue": null,
      "comment": null
    },
    {
      "fieldPath": "rx.medications[0].frequency",
      "verdict": "correct",
      "correctedValue": "twice daily",
      "comment": "API extracted 'bid' but should be 'twice daily'"
    }
  ]
}
```

### result (thread_review — kaira future)
```json
{
  "overallVerdict": "rejected",
  "notes": "",
  "items": [
    {
      "threadId": "thread-123",
      "evaluatorType": "correctness",
      "originalVerdict": "PASS",
      "humanVerdict": "SOFT FAIL",
      "comment": "Calorie count was off by 30%"
    }
  ]
}
```

### summary (segment_review)
```json
{
  "totalItems": 50,
  "accepted": 45,
  "rejected": 2,
  "corrected": 3,
  "unreviewed": 0,
  "overallVerdict": "accepted_with_corrections",
  "adjustedMetrics": {
    "match": 96.0,
    "wer": 4.0,
    "cer": 1.8
  }
}
```

### summary (field_review)
```json
{
  "totalItems": 20,
  "accepted": 18,
  "rejected": 1,
  "corrected": 1,
  "unreviewed": 0,
  "overallVerdict": "accepted_with_corrections",
  "adjustedMetrics": {
    "fieldAccuracy": 95.0,
    "recall": 100.0,
    "precision": 95.0,
    "wer": 4.0,
    "cer": 1.8
  }
}
```

## Verification

- `curl -X PUT localhost:8721/api/eval-runs/{ai_run_id}/human-review -H 'Content-Type: application/json' -d '{...}'` → 200
- `curl localhost:8721/api/eval-runs/{ai_run_id}/human-review` → returns saved review
- Second PUT overwrites → same ID returned
- PUT with non-existent ai_run_id → 404
- PUT with eval_type != full_evaluation → 400
