# Phase 3: Verification

## Pre-commit Checks

### 1. Python syntax

```bash
python -c "from app.services.seed_defaults import KAIRA_BOT_EVALUATORS; print(f'{len(KAIRA_BOT_EVALUATORS)} evaluators')"
```

Expected: `8 evaluators`

### 2. Schema generation roundtrip

Verify each new evaluator's `output_schema` produces valid JSON Schema:

```bash
python -c "
from app.services.seed_defaults import KAIRA_BOT_EVALUATORS
from app.services.evaluators.schema_generator import generate_json_schema
for e in KAIRA_BOT_EVALUATORS:
    schema = generate_json_schema(e['output_schema'])
    main = [f for f in e['output_schema'] if f.get('isMainMetric')]
    assert len(main) == 1, f'{e[\"name\"]}: expected 1 isMainMetric, got {len(main)}'
    assert schema.get('type') == 'object'
    assert schema.get('required')
    print(f'  OK: {e[\"name\"]} — {len(schema[\"required\"])} fields, main={main[0][\"key\"]}')
"
```

Expected: 8 lines of `OK`, each with the correct main metric key:
- Chat Quality Analysis → `overall_score`
- Health Accuracy Checker → `accuracy_score`
- Empathy Assessment → `empathy_score`
- Risk Detection → `risk_level`
- Domain Routing Accuracy → `routing_accuracy`
- Data Faithfulness → `faithfulness_score`
- CGM-Food Correlation Quality → `correlation_score`
- Date Handling Accuracy → `date_accuracy`

### 3. Variable resolution check

Verify all prompts use only `{{chat_transcript}}` (the only registered kaira-bot variable):

```bash
python -c "
import re
from app.services.seed_defaults import KAIRA_BOT_EVALUATORS
for e in KAIRA_BOT_EVALUATORS:
    vars = set(re.findall(r'\{\{(\w+)\}\}', e['prompt']))
    assert vars == {'chat_transcript'}, f'{e[\"name\"]}: unexpected vars {vars}'
    print(f'  OK: {e[\"name\"]}')
"
```

### 4. Name uniqueness

```bash
python -c "
from app.services.seed_defaults import KAIRA_BOT_EVALUATORS
names = [e['name'] for e in KAIRA_BOT_EVALUATORS]
assert len(names) == len(set(names)), f'Duplicate names: {[n for n in names if names.count(n) > 1]}'
print(f'  OK: {len(names)} unique evaluator names')
"
```

### 5. Lint

```bash
cd backend && python -m flake8 app/services/seed_defaults.py --max-line-length 120
```

## Runtime Verification

### 6. Seed endpoint

Start the backend, then call the seed endpoint:

```bash
curl -s -X POST "http://localhost:8721/api/evaluators/seed-defaults?appId=kaira-bot" \
  -H "Authorization: Bearer <token>" | python -m json.tool
```

Expected: Returns the 4 new evaluators (existing 4 are skipped). On second call, returns empty list (all 8 already exist).

### 7. List endpoint

```bash
curl -s "http://localhost:8721/api/evaluators?appId=kaira-bot" \
  -H "Authorization: Bearer <token>" | python -m json.tool | grep '"name"'
```

Expected: All 8 evaluator names listed.

### 8. Smoke test — run one evaluator

In the UI:
1. Open a kaira-bot chat session that contains a CGM or food conversation
2. Run the "Domain Routing Accuracy" evaluator
3. Verify:
   - Job completes without error
   - `routing_accuracy` score appears in the header
   - `total_turns` and `misrouted_turns` appear as cards
   - `analysis` field is populated in the detail view
   - EvalRun summary has `overall_score` populated

### 9. Idempotency

Call seed endpoint again → no new evaluators created, no errors.

## What "Pass" Looks Like

- [x] `KAIRA_BOT_EVALUATORS` has 8 entries
- [x] All 8 produce valid JSON Schema with exactly 1 `isMainMetric`
- [x] All prompts use only `{{chat_transcript}}`
- [x] No duplicate names
- [x] Seed endpoint creates exactly 4 new evaluators for a user who already has the original 4
- [x] Each new evaluator runs successfully on a real chat session
- [x] No changes to any file other than `seed_defaults.py`
