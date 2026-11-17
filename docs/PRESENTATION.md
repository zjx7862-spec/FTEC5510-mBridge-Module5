# Explaining Module 5 to teammates

## What it does

Module 4 asks which payment should be considered first. Module 5 asks how to fund that payment when current RMB cannot fund any remaining eligible instruction. The engine executes the advice.

S3 keeps arrival order and adds waiting decisions. S4 combines the same funding rule with Module 4's dynamic order. S3 versus S1 and S4 versus S2 isolate the waiting mechanism under their respective ordering rules.

## Decision sequence

1. Take the funding-blocked target in strategy order.
2. Calculate its RMB gap using engine available cash.
3. Check already committed FX; do not duplicate covered funding.
4. Accumulate notified inflows and timed pending FX.
5. WAIT only when sufficient funds plus confirmation and safety time meet the deadline.
6. Otherwise check an executable FX trade. Record risk even if completion will be late.
7. If FX is infeasible, keep the instruction queued and reassess later.

## Three reproducible cases

Common teaching inputs: RMB 0, reserve 0, HKD 1000, rate 1, fixed fee HKD 1, FX delay 5 seconds, confirmation 2 seconds, safety 2 seconds. Payment A arrives at second 1, needs RMB 100, and expires at second 30.

| Case | Advice and actual outcome |
|---|---|
| wait | Notified RMB 100 arrives at second 10. WAIT; submit at 10; settle at 12; no FX |
| fx | No notice. Buy RMB 100 at second 1, commit HKD 101, complete at 6, settle payment at 8; final HKD 899 |
| infeasible | HKD 0 and no notice. No executable FX; payment remains queued at endpoint 100 |

These are mechanism checks, not estimated performance for real banks. Inputs are constructed in verify.py; actual traces are under evidence/wait, fx and infeasible.

## What this revision improves

Late or un-timed pending FX is now explicit in risk evidence. Mixed pending/new funding is not assumed timely merely because the new trade is fast. Logs record changed advice without timestamp-only duplicates. Reviews do not create redundant shifted chains. The saved audit checks the complete pilot matrix and independently replays every cash-changing event, including intermediate commitments.

## What remains a team decision

Historical rolling forecasts, FX failure accounting and formal fee/configuration alignment remain deferred. Official service metrics and formal multi-seed experiments belong to Module 6. Do not claim one strategy is universally superior from the pilot table.
