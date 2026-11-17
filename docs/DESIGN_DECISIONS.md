# Deferred experimental decisions and proposal alignment

Status: existing notified-inflow decisions, successful FX execution and the inherited pilot fee rules remain the defaults. The user approved this scope on 2026-11-16. The proposals below are specifications for team discussion, not implemented features.

## Historical rolling forecasts

The proposal mentions observed history, notified instructions and a frozen rolling estimation window. The engine currently exposes notified, uncredited inflows within a lookahead window. It does not expose an observation-stamped historical stream. A lookahead limit is not a statistical forecasting model, and inflow_confidence_threshold does not create calibrated confidence.

Recommended next experiment: keep notified_only as the primary reproducible baseline; add a separately named historical_forecast variant only after agreement on data and validation. The engine must reveal credited inflow history with inflow_id, observed_at, arrival_time, amount and notice metadata as of the decision time. No generated but unrevealed future entries are allowed.

Candidate estimator for a separate experiment: estimate the arrival frequency and amount distribution over a past-only fixed window, evaluate cumulative inflow forecasts at fixed future horizons, and calibrate a conservative predictive bound on pilot data. A compound-arrival assumption, minimum sample count, confidence target and horizon grid must be explicitly agreed and validated; an expected amount alone is not sufficient evidence of timely funds.

Cold start, empty history or insufficient calibration data must fall back to notified_only; do not predict an unobserved credit with invented certainty. Freeze the window, minimum sample count and calibration settings before formal seeds. Recompute only from the observable history at each review and record the observation cutoff.

Avoid double counting: notified IDs are counted explicitly once. A historical background forecast must model only a separately identifiable unnotified component (requiring historical notification labels), or use a documented total-forecast combination rule. Do not simply add total forecast cash to known notices. Without labels or a justified combination, retain notified_only rather than implement a biased sum.

Team decisions required: input/history interface (Module 3), statistical assumptions and calibration (Modules 1/2/5), combination rule and error evidence, and separate reporting (Module 6). No historical forecast was added in this revision.

## FX failure accounting specification for review

No FX failure probability or failure event has been invented. Existing payment confirmation failures are separate and remain supported.

A future engine-owned FX failure event must reference an active fx_id and happen once. Remove it from pending FX; release its HKD commitment; credit no RMB and charge no FX principal for a wholly failed trade. If a fee is charged, deduct only the explicitly configured failure fee and record it separately. If the underlying execution model permits partial fills, it requires a separate agreed model rather than treating a partial fill as a full failure.

Capacity restoration is an unresolved economic choice: a reusable reserved cumulative quota may be released; a limit on all initiated requests may remain consumed. Do not restore or consume it silently. The team must define which rule cumulative means before implementation. Per-trade capacity remains a limit rather than a shared balance.

Keep the target payment queued unless it was independently submitted using other funds. Reassess the whole queue after failure under the same strategy and record FX_FAILED, released commitment, any charged fee, quota treatment and the new advice. Failure paths must be injected deterministically for testing; random shocks need stable trade/payment matching before cross-strategy claims.

## Configuration differences

The following baseline comparison uses vendor/pilot/baseline/seed_1001/config.json. It is a teaching pilot, not the formal proposal baseline. Other scenarios intentionally change constraints; their original files and manifests remain unchanged.

| Item | Proposal | Current pilot baseline | Required agreement |
|---|---|---|---|
| FX rate RMB/HKD | 0.92 | 0.90 | Freeze a shared formal value |
| Proportional FX fee | 3 bps | No separate proportional fee | Define fee base, currency and rounding |
| Spread | Not the same as the 3 bps fee | 15 bps effective-rate haircut | Keep fee and spread distinct |
| Fixed fee HKD | Specified separately | 80 | Confirm whether formal trades include it |
| FX completion | 20 seconds; longer in stress | 120 seconds | Use consistent baseline/stress definitions |
| Payment confirmation | 10 seconds | Engine default 10 | Explicitly resolve and record |
| Counterparty RMB capacity | 50 million baseline; 10 million constrained | 5 million, per_trade default | Confirm amount and quota interpretation |
| Opening RMB | 20 million | 6 million | Formal baseline versus funding scan |
| RMB reserve | 5 million | 0.8 million | Confirm common reserve |
| Opening HKD | 100 million | 15 million total, 0.5 million buffer | Distinguish total and available |
| Safety margin | Calibrated before formal tests | 180 seconds | Freeze from pilot; do not retune on formal results |
| Forecast window | Past-only rolling estimation window | No historical estimator; lookahead 7200 seconds | These are different concepts |
| Notice filter | Current information only | Minimum advance notice 0 seconds | Confirm shared information contract |
| Confidence | Requires supported forecast reliability | Threshold 0.75 present but unused | Do not claim calibrated confidence |
| Funding buffer | 0 baseline | Engine default 0 | Common value for every strategy |
| Service targets | Completion minimum and urgent deadline breach maximum | Overall completion, overdue fraction and P95 fields | Agree exact scope/denominators with Module 6 |

The current seven pilot folders are baseline, delayed_inflows, fx_capacity_shock, large_payments, low_rmb_liquidity, payment_surge and tight_deadlines. These are not a one-for-one implementation of the proposal's six stress categories (for example urgent-share and high-FX-cost scenarios). Record the mapping and add separate formal configurations only after the team confirms the scenario design. Do not relabel these pilot runs as a full proposal scenario study.

Formal configuration changes should live outside vendor/pilot with new dataset/config identities and updated manifests produced by the input owner. Preserve fair paired inputs across strategies. Formal 30-seed estimates, confidence intervals, initial-funding scans and sensitivities remain Module 6's coordinated experiments.
