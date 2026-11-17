# FTEC5510 Module 5 Funding Decisions

A reproducible course delivery for waiting versus HKD-to-RMB top-up, integrated with the team's Module 3 engine and Module 4 ranking. Python 3.10+; standard library only.

## Quick start in Windows PowerShell

Open PowerShell in this directory:

```powershell
python --version
python -m unittest discover -s tests -v
python verify.py
python audit_saved.py
python run_engine.py --dataset vendor/pilot/low_rmb_liquidity/seed_1001 --strategy all --out module3_outputs
```

Run `verify.py` before `audit_saved.py` on a fresh delivery. Verification recreates three hand cases and 84 pilot runs: seven scenarios, three seeds and S1/S2/S3/S4. The saved audit rejects zero/incomplete runs, missing outputs, inconsistent identities, wrong inputs and fallbacks. It independently replays cash movements at every recorded event. Full pilot traces are regenerated locally and excluded from Git.

## Implemented scope

- S0: strict FIFO; S1: skippable FIFO; S2: real Module 4 ordering. All use immediate FX mode.
- S3 uses arrival order and waiting/FX decisions. S4 uses the same funding function with real Module 4 ordering.
- WAIT requires sufficient notified inflows and/or timed pending FX, plus confirmation and safety time, before the deadline.
- Pending funds never enter available cash before completion. Full pending coverage prevents duplicate FX, even if late; the evidence separately reports lateness or unknown timing.
- Partial pending coverage reduces the new top-up. Minimum trade size may cause overshoot; no automatic splitting above limits.
- Infeasible FX leaves obligations queued. Executable FX is still attempted when expected to be late.
- Only the engine changes balances, locks and payment status. Funding advice is deterministic and does not mutate inputs.

This is a **notified-inflow implementation**, not a historical forecasting model. FX failures and the proposal's formal fee model remain unimplemented pending team agreement. The user confirmed retaining the existing mechanism for this revision. Existing pilot configurations are not the proposal's formal baseline. No official Module 6 metrics or formal 30-seed conclusions are claimed.

## Files and handoff

| File | Purpose |
|---|---|
| `module5_funding.py` | Pure funding advice |
| `vendor/m3engine/` | Pinned Module 3 with a reviewed local patch |
| `vendor/module4_rank.py`, `vendor/m4rank/` | Real Module 4; four documentation phrases translated to English, ranking behavior unchanged |
| `vendor/pilot/` | Original inputs and manifests; unchanged |
| `validation.py`, `audit_saved.py` | Matrix coverage and event-time accounting replay |
| `verify.py`, `tests/` | Hand cases, pilots and regression checks |
| `docs/HANDOFF.md` | Interface, parameters, patch application and ownership |
| `docs/DESIGN_DECISIONS.md` | Deferred forecasting/failure specifications and configuration differences |
| `docs/PRESENTATION.md` | Short explanation and examples for teammates |
| `docs/VALIDATION.md` | Actual verification results and before/after changes |
| `evidence/` | Saved test records, comparison tables and three hand cases |

## Logging policy

Log consecutive semantic transitions, not timestamp-only repeats. Target, action, reason code, amount, source credit evidence and deadline risk are included in the signature; only the observation timestamp is excluded. Returning from target B to target A is logged again. Emitted records retain their actual time. This is an audit of changed advice, not a count of all reviews or executed trades. TOP_UP advice and FX execution are separate events.

## Repository and download

Public repository: https://github.com/zjx7862-spec/FTEC5510-mBridge-Module5

Browse the source and docs directly, or download `Module5-delivery.zip` and extract it before running the commands above. The ZIP includes the same runnable source, test suite, pinned dependencies, original pilot inputs and compact verification evidence; generated pilot traces and caches are excluded. Regenerate all traces with `python verify.py`.

Upstream source attribution and version pins are in docs/HANDOFF.md. No additional upstream license is asserted. This is a course collaboration delivery, not a production banking system.
