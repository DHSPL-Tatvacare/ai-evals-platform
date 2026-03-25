# Voice-RX API Flow Metrics — Fix & Enhancement Plan

## Problem Statement

The MetricsBar (Match %, WER, CER) shows **100% Match, WER 0.00, CER 0.00** for API flow evaluations. This is a bug — it's comparing empty string vs empty string because the metrics system was built for upload flow (segment-based transcripts) and doesn't handle API flow (fullTranscript strings).

Meanwhile, the SemanticAuditView header shows **29% Accuracy** which IS correct — it counts `match: true` from `fieldCritiques`. But this metric lives only in the audit view, not in the MetricsBar.

## Current Architecture

```
ListingPage.tsx
  └─ useListingMetrics(listing, aiEval) → ListingMetrics | null
       └─ computeAllMetrics(listing.transcript, judgeTranscriptData)
            ├─ transcriptToText(t) = t.segments.map(s => s.text).join(' ')  ← BUG: empty for API flow
            ├─ calculateWERMetric(originalText, llmText)
            ├─ calculateCERMetric(originalText, llmText)
            └─ calculateMatchMetric(wer) = 100 - WER
  └─ MetricsBar
       └─ MetricCard × 3 (Match, WER, CER)
```

### Why it's broken for API flow

| Data source | Upload flow | API flow |
|---|---|---|
| `listing.transcript.segments` | Array of `{text, speaker, ...}` | **Empty array `[]`** |
| `listing.transcript.fullTranscript` | Concatenated text | API's raw transcript string |
| `aiEval.judgeOutput.segments` | Array of segments | **null** |
| `aiEval.judgeOutput.transcript` | Full text | Judge's full transcript |

`transcriptToText()` uses `.segments.map(s => s.text)` → empty for API flow → WER("","") = 0.

## Proposed Metrics for API Flow

### Metric 1: Field Accuracy (replace "Match")
- **What**: Percentage of compared fields where API and Judge agree
- **Formula**: `fieldCritiques.filter(match).length / fieldCritiques.length * 100`
- **Data source**: `aiEval.critique.fieldCritiques` (already in DB)
- **Why**: This is the primary metric — did the API extract the right clinical data?
- **Already computed in**: `SemanticAuditView.tsx:88-95` and `_build_summary()` in `voice_rx_runner.py:940-951`

### Metric 2: Transcript WER (fix existing)
- **What**: Word Error Rate between API transcript and judge transcript
- **Formula**: Levenshtein distance on word arrays / reference word count
- **Data source**: `apiResponse.input` (API transcript) vs `judgeOutput.transcript` (judge transcript)
- **Why**: Measures raw transcription quality before structured extraction
- **Fix**: Use `fullTranscript` / `apiResponse.input` strings directly instead of segments

### Metric 3: Transcript CER (fix existing)
- **What**: Character Error Rate between API transcript and judge transcript
- **Formula**: Levenshtein distance on char arrays / reference char count
- **Data source**: Same as WER
- **Fix**: Same as WER

### Metric 4: Extraction Recall
- **What**: Of everything the judge identified, how much did the API also capture?
- **Formula**: `entries_with_api_value / total_entries` where api_value !== "(not found)"
- **Data source**: `aiEval.critique.fieldCritiques`
- **Why**: Catches omissions — API missing medications, diagnoses, etc.

### Metric 5: Extraction Precision
- **What**: Of everything the API extracted, how much was semantically correct?
- **Formula**: `matched_entries_with_api_value / entries_with_api_value`
- **Data source**: `aiEval.critique.fieldCritiques`
- **Why**: Catches hallucinations — API inventing medications that weren't mentioned

## Files to Modify

See individual plan files:
- `01_TYPES_AND_COMPUTATION.md` — types, computation logic, hook changes
- `02_UI_METRICS_BAR.md` — MetricsBar and MetricCard changes
- `03_BACKEND_SUMMARY.md` — Backend `_build_summary` additions (optional)

## Example: Listing 435e078b

| Metric | Current (broken) | After fix |
|---|---|---|
| Field Accuracy | Not in MetricsBar (29% only in audit view) | **29%** (9/31 fields correct) |
| Transcript WER | 0.00 (empty vs empty) | Actual WER from Hindi transcript comparison |
| Transcript CER | 0.00 (empty vs empty) | Actual CER from Hindi transcript comparison |
| Extraction Recall | Not computed | **71%** (22/31 entries have API values) |
| Extraction Precision | Not computed | **41%** (9/22 API-extracted values are correct) |
