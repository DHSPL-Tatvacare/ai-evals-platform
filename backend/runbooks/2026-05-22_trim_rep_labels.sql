-- One-time backfill: trim + collapse whitespace on existing rep/stage labels.
-- Run AFTER deploy (ingestion now writes clean labels); not part of Alembic.

UPDATE analytics.fact_lead_activity
SET actor_label = regexp_replace(trim(actor_label), '\s+', ' ', 'g')
WHERE activity_type = 'call'
  AND actor_label IS NOT NULL
  AND actor_label <> regexp_replace(trim(actor_label), '\s+', ' ', 'g');

UPDATE analytics.crm_call_record
SET rep_name = regexp_replace(trim(rep_name), '\s+', ' ', 'g')
WHERE rep_name IS NOT NULL
  AND rep_name <> regexp_replace(trim(rep_name), '\s+', ' ', 'g');

UPDATE analytics.dim_lead
SET assigned_rep_label = regexp_replace(trim(assigned_rep_label), '\s+', ' ', 'g')
WHERE assigned_rep_label IS NOT NULL
  AND assigned_rep_label <> regexp_replace(trim(assigned_rep_label), '\s+', ' ', 'g');
