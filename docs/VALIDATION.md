# Validation and revision record

Review date: 2026-11-16. This revision retains the existing experiment scope. Prior source code, documents and the comparison table were backed up outside the delivery in Module5-review-backup-20261116. Original pilot inputs are unchanged.

## Checks actually completed

- The original 18 tests were rerun and passed before editing.
- The expanded suite covers pending FX timing/uncertainty, mixed credits, no recursive evidence, semantic transitions, S0/S1 behavior, actual engine information filtering, bounded review scheduling, intermediate accounting corruption and fail-closed saved audits. See evidence/tests.txt for the exact count and output.
- Three hand cases were rebuilt and audited.
- All 84 pilots (seven scenarios x three seeds x four strategies) were rebuilt with real modules.
- Every saved event was independently replayed to reconcile RMB/HKD totals, reserves, locks, commitments and available balances. Coverage, result identities, comparison hashes and source manifests were checked.
- The pinned original Module 3 engine SHA256 was checked; git apply --check and actual apply succeeded in an isolated folder; the resulting bytes matched the delivered engine.
- All 84 original pilot input/config/manifest files matched their pre-review SHA256 hashes.

## Before versus after

See evidence/pilot_comparison_before.csv, pilot_comparison.csv and pilot_changes.csv. All 84 runs retained the same completed/unfinished/ineligible counts, FX initiation counts and FX costs. Only recorded funding-decision counts changed. Those counts now describe consecutive semantic transitions, not every repeated review.

For baseline seed 1001: S1 decision records fell from 374 to 105, S2 from 372 to 115, S3 from 934 to 95 and S4 from 929 to 109. This is a logging/scheduling improvement, not an economic performance gain. Unchanged aggregate counts do not establish identical per-payment timing or universal strategy quality.

## Changes

1. Full pending coverage reports timely, late or unknown timing without duplicate FX.
2. Partial pending plus a new trade is timed as joint coverage; fast new FX alone cannot hide late required pending funds.
3. Pending evidence is a bounded identity/amount/time summary, never a recursive copy of historic reasons.
4. The engine logs consecutive semantic changes, ignoring only observation time, and preserves target switches and risk transitions.
5. An existing earlier review satisfies a later request; no shifted review chain is added unnecessarily.
6. Verification requires exact input/run coverage. Saved summaries are now regenerated along with CSVs. Missing or corrupt results fail explicitly.
7. Account replay checks intermediate states, not only the last balance. Negative tests intentionally corrupt results and confirm rejection.
8. Delivery/Git claims were corrected. No repository, commit or publication was invented. Source/data instructions are English.

## Boundaries

These checks support a reproducible notified-inflow midterm delivery, not complete implementation of the original proposal. No statistical historical predictor, FX failure model, formal fee revision, official Module 6 metrics or formal multi-seed inference was added. No GitHub upload occurred. Passing tests does not prove the absence of all defects.
