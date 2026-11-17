# Module 5 interface and integration handoff

## Pinned sources

- Module 3: https://github.com/wangzai-dao/FTEC5510-mBridge-Module3, commit `ea57cc82c01c86a1bd02aeae7247af4644a6df81`.
- Module 4: https://github.com/yymdqq/FTEC5510-mBridge-Module4, commit `191bffd56a656544fa52a659d02652b42498fe80`.

Module 4's ranking behavior is retained; four documentation phrases were translated into English. The Module 3 engine changes are supplied in `module3.patch`. The portable patch checker downloads only the pinned original file and verifies its SHA256 before applying the patch in a temporary folder.

## Contract v1.1

`decide_funding(queue, state, known_inflows, config, mode)` returns:

| Field | Meaning |
|---|---|
| `action` | WAIT / TOP_UP / NO_ACTION |
| `target_payment_id` | Target or null |
| `topup_rmb` | Decimal, rounded to cents |
| `reason` | Stable reason code followed by `;evidence=` and JSON |
| `next_check_time` | Future integer second |

The engine passes queued payments in actual strategy order. S0 passes only its head. S1/S3 use arrival order; S2/S4 reuse Module 4. Funding is triggered after the engine submits all currently payable eligible instructions (S0 stops at its head). Queue fields: payment_id, arrival_time, amount_rmb, priority, deadline_time, submit_time, waiting_time. Eligibility is already filtered by the engine; direct callers may supply eligible=false.

State includes current time, RMB total/reserve/locks/available, HKD total/commitments/available, counterparty capacity and pending FX. Pending FX includes topup_rmb and expected_completion_time. Missing times yield indeterminate timing risk; they are not treated as timely cash.

`known_inflows` is filtered by the engine to already-notified, uncredited entries within max_lookahead_sec and minimum_advance_notice_sec. It contains inflow_id, arrival_time and amount_rmb. An optional notice_time is checked defensively; a future or null notice is not accepted. Do not pass the full future input file. Decisions use no private future generator data.

Modes: immediate for S0/S1/S2; wait_or_topup for S3/S4. All strategies use the same funding arithmetic. Only the engine applies money/status changes.

## Pending FX and deadline evidence

Evidence includes gap, pending amount, a bounded FX summary (id/amount/expected completion), pending_sufficient_at, sufficient_at, timing uncertainty, confirmation time, safety time and deadline_risk. Risk is true for known late coverage, false for known timely coverage, and null when the supplied times cannot establish coverage. Partial pending plus new FX must jointly cover the gap before timing can be called timely. Full pending coverage prevents duplicate top-up regardless of risk.

No historic reason strings are embedded in pending summaries. Notified credits can justify WAIT but are not subtracted from the immediate top-up amount. Successful FX does not reserve money or priority for its original target.

## Parameters

| Config field | Use / default |
|---|---|
| fx_rate | RMB per HKD |
| fx_spread_bps | Effective-rate haircut, default 0 |
| fx_fee_fixed_hkd | Fixed HKD fee, default 0 |
| fx_topup_min_rmb / fx_topup_max_rmb | Trade limits |
| fx_counterparty_capacity_rmb | Capacity |
| engine_parameters.fx_counterparty_capacity_mode | per_trade default; cumulative is consumed at initiation |
| fx_execution_delay_sec | Time to FX completion |
| payment_confirmation_delay_sec | Nested engine_parameters overrides top-level; engine default 10 |
| fx_safety_buffer_sec | Same deadline safety margin for waiting and FX; default 0 |
| fx_buffer_rmb | Nested engine_parameters overrides top-level; default 0 |
| funding_review_interval_sec | Periodic review, default 60 |
| prediction_parameters.max_lookahead_sec | Engine information filter, not a statistical forecast |
| prediction_parameters.minimum_advance_notice_sec | Engine notice filter |
| fx_quote_valid | Static boolean gate, default true; not a quote expiry model |

Available RMB=max(0,total-locks-reserve). Available HKD=max(0,total-commitments-buffer). New top-up=max(minimum,gap+buffer-pending), unless pending already covers gap. Reject above maximum/capacity; no splitting. Effective rate=fx_rate*(1-spread_bps/10000). Principal=RMB/effective rate rounded HALF_UP to HKD cents; add fixed fee. These are inherited pilot rules, not the final proposal fee specification.

## Engine changes and scheduling

All strategies load Module 5, receive actual ordering, and log suggested TOP_UP separately from execution. The engine exposes expected FX completion, checks static quote validity again and avoids topping up a covered gap. Review requests are scheduled only when no existing review occurs sooner or at that time; this removes redundant shifted chains while retaining requested earlier checks. No past/same-time review is scheduled. Reviews are not funding events by themselves and cannot credit money.

Decision logs compare consecutive semantic signatures across targets. Only evidence.t is ignored. All changed amounts, sources, reasons, targets and risk states remain observable. Failure/non-funding actions remain in the queue.

## Apply the patch

In a clean checkout of the pinned Module 3 commit, from its repository root:

```powershell
git apply --check C:/path/to/Module5-delivery/docs/module3.patch
git apply C:/path/to/Module5-delivery/docs/module3.patch
$env:PYTHONPATH = 'C:/path/to/Module5-delivery;C:/path/to/module4'
python module3/run_engine.py --dataset module3/fixtures/pilot/low_rmb_liquidity/seed_1001 --strategy all
```

Alternatively run this delivery's root run_engine.py, which selects vendor explicitly. Do not accidentally mix engines. Inspect using_fallback_module5=false, and using_fallback_module4=false for S2/S4. The standalone delivery runner's status messages were corrected for the new S0/S1 dependency.

## Ownership and limitations

Module 3 owns execution and failure events; Module 4 owns order; Module 5 owns advice; Module 6 owns official metrics. Give Module 6 events, balances, payment_results, fx_trades and the summary/config identity. Advice is not proof of an executed trade.

The existing notified-inflow mode, deterministic successful FX, pilot fees and original input files remain in use, as confirmed by the user for this revision. See DESIGN_DECISIONS.md before changing historical forecasting, FX failure accounting or formal parameters. Confirmation failures exist upstream, but RNG draws are not paired by payment across differently ordered strategies; pilot failure probability remains zero.
