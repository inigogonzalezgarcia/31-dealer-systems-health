# Data format

Put the files in one folder and run `python -m dealerhealth review <folder>`. Only `dealers.csv` is required; every other file adds its checks when present. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the common alternatives below are accepted.

## dealers.csv (required)

The dealer register, usually kept by the network development team.

| Column | Also accepted | Notes |
|---|---|---|
| Dealer code | dealer id, dealer, code, codigo | Must match the code in the other files |
| Name | dealer name, nombre, razon social | |
| Country, City | pais, ciudad | |
| Type | kind, dealer type | `service only` dealers send no vehicle sales; the review lists that feed as information |
| DMS, DMS version | dms product, version | Compared with `supported_dms` and `dms_end_of_support` |
| Status | estado | `active`, `onboarding` or `terminated` (also: activo, alta, baja, closed) |
| Go live | go-live date, alta | For onboarding dealers, the planned opening |
| End date | terminated, baja | For terminated dealers |
| Area manager | manager, responsable | Shown in the red-dealer list |

## interface_runs.csv

One row per run of a DMS interface, for at least `window_days` (14 by default).

| Column | Also accepted | Notes |
|---|---|---|
| Dealer code | dealer | |
| Interface | feed, job, flow | `repair_orders`, `warranty_claims`, `parts_orders`, `vehicle_sales`, `stock`; close names (RO, Warranty, Parts orders) work |
| Run at | started, timestamp | `YYYY-MM-DD HH:MM` or ISO |
| Status | result | ok / partial / failed (success, warning, error, timeout also accepted) |
| Records, Errors | rows, rejected | Records accepted and records rejected in that run |

## warranty_claims.csv

| Column | Also accepted | Notes |
|---|---|---|
| Claim number | claim id | |
| Dealer code, VIN | bastidor | |
| Repair date | repair order date | Starts the submission clock (`claim_submit_days`) |
| Submitted | submission date | Empty for drafts |
| Status | claim status | draft, submitted, info requested, accepted, rejected, paid (open, returned, approved, declined, credited also accepted) |
| Status date | last update, decision date | Starts the clocks for information requests and payment |
| Labour op | operation, op code | Used with the VIN to spot duplicates |
| Amount | importe | Decimal comma or point |
| Reason | rejection reason, info requested | |
| Paid date | payment date | |

## catalogue_status.csv

One row per dealer with the parts catalogue and price file its DMS last confirmed: `Dealer code`, `Catalogue version`, `Catalogue date`, `Price file version`, `Price file date`. Dealers missing from this file are listed as unknown.

## onboarding.csv

The go-live checklist of dealers in onboarding: `Dealer code`, `Item`, `Done` (yes/no). Items are compared with `onboarding_items` in the settings.

## settings.json

All keys are optional. The defaults are in `dealerhealth/model.py`; the demo's file in `sample_data/` shows every key.

| Key | Default | Meaning |
|---|---|---|
| `brand`, `as_of`, `currency` | | Title, review time (`YYYY-MM-DD HH:MM`) and currency symbol |
| `interfaces` | five feeds | Per interface: `stale_hours` without a successful run, and `critical` (a critical feed that stops is a critical finding) |
| `window_days`, `error_rate_max_pct`, `silent_days` | 14, 5, 3 | Interface error rate and empty-run limits |
| `supported_dms`, `dms_end_of_support`, `eos_warn_days` | | Certified DMS versions per product; end-of-support dates as `"Product version": "YYYY-MM-DD"` |
| `claim_submit_days`, `claim_warn_days` | 30, 7 | Submission limit after the repair date, and how early to warn |
| `claim_pending_days`, `info_request_days`, `unpaid_days` | 15, 10, 30 | Ageing limits for the brand's queue, unanswered information requests and accepted claims not paid |
| `rejection_rate_max_pct`, `min_claims_for_rate`, `claims_window_days` | 12, 10, 90 | Rejection-rate limit per dealer |
| `duplicate_window_days` | 30 | Same VIN and labour op within this many days |
| `catalogue_version`, `catalogue_released`, `catalogue_grace_days`, `catalogue_versions` | | Current catalogue, release date, grace period, and the list of versions newest first |
| `price_version`, `price_released`, `price_grace_days` | | Current price file |
| `onboarding_items`, `onboarding_warn_days`, `onboarding_critical_days` | six items, 21, 7 | Go-live checklist |
| `owners` | | Owner per area: interfaces, warranty, payments, parts, dms, onboarding |
