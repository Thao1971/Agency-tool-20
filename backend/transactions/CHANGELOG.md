# M&A Radar — Changelog & Architecture

## Data Model Rules (frozen)

### `visible_in_cis`
Controls visibility in CIS M&A Radar and company profiles.
- `true` → transaction appears in `GET /api/v1/transactions/approved-for-cis`
- `false` or absent → transaction does NOT appear in CIS
- Set by: "Publicar en CIS", "Publicar todas en CIS" (mass)
- Cleared by: soft-delete, withdraw-from-cis

### `review_status`
Controls editorial quality and Analytics inclusion.
- Values: `pending`, `reviewed`, `approved`
- Only `reviewed` or `approved` enter Analytics/KPIs
- Independent of `visible_in_cis` — a transaction can be visible in CIS while still pending review

### `deleted`
Universal exclusion flag. `deleted=true` excludes from:
- All active tables and views
- `GET /api/v1/transactions/approved-for-cis`
- Stats bar counters
- Analytics aggregations
- Exports (JSON/Excel)
- Duplicate scanning
- Never physical delete — always soft-delete with `deleted_at`, `deleted_by`, `delete_reason`

### `publish_status`
Formal editorial publication status.
- `not_published` → default
- `ready_to_publish` → manually marked as ready
- `approved_for_cis` → formally published with full validation
- `removed_from_cis` → withdrawn with mandatory reason

### `cis_sync_status`
Tracks sync state after publication.
- `approved_for_cis` → in sync
- `pending_update` → edited after publish, needs "Actualizar en CIS"
- `removed_from_cis` → withdrawn

## Endpoint Contract

### `GET /api/v1/transactions/approved-for-cis` (public, no auth)
Returns transactions where:
```
(publish_status = "approved_for_cis" OR visible_in_cis = true)
AND deleted != true
```

### `GET /api/v1/transactions/analytics` (auth required)
Only counts transactions where:
```
deleted != true
AND review_status IN ["reviewed", "approved"]
```

## Principle
**Agency Tool governs** editorial review, publication, deletion, and duplicates.
**CIS only consumes** and renders visible transactions — no editorial logic.

## Changelog

### v2.1 (May 2026)
- Added `visible_in_cis` field for mass pre-publish
- Added `POST /publish-all-cis` endpoint
- Analytics now filters by `review_status in ["reviewed", "approved"]`
- Soft-delete clears `visible_in_cis` automatically
- Added `POST /{tx_id}/mark-ready` for manual "Preparada" status
- Added `POST /dedupe/{id}/merge-reverse` (keep B, discard A)
- `keep-separate` now clears `dedupe_status` on both transactions
- Merge adds audit log with kept/discarded IDs
- Country translation (Spain→España, UK→Reino Unido, etc.)
- Dates in DD/MM/YYYY format throughout UI

### v2.0 (April 2026)
- Full editorial pipeline: import → normalize → dedupe → match → classify → review → publish → sync
- 4 views: Todas, Necesitan revision, Preparadas, Publicadas en CIS + Analytics
- Entity matching (CIF, domain, fuzzy)
- AI classification copilot (GPT-5.2)
- Batch classification with review queue
- CIS publication with validation checklist
- Withdrawal with mandatory reason
- Multiple sources per transaction
- Editorial description (summary, strategic_rationale, editorial_notes)
