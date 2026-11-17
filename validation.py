"""Strict coverage checks and event-time ledger replay; not official metrics."""
import csv
import hashlib
import json
from decimal import Decimal as D
from pathlib import Path

SCENARIOS = ('baseline', 'delayed_inflows', 'fx_capacity_shock', 'large_payments',
             'low_rmb_liquidity', 'payment_surge', 'tight_deadlines')
SEEDS = (1001, 1002, 1003)
STRATEGIES = ('S1', 'S2', 'S3', 'S4')
FILES = ('payment_results.csv', 'events.csv', 'balances.csv', 'fx_trades.csv', 'run_summary.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def input_digest(path):
    return hashlib.sha256(b''.join((path / f).read_bytes()
                         for f in ('config.json', 'payments.csv', 'inflows.csv'))).hexdigest()


def pilot_inputs(root):
    expected = {Path(s) / ('seed_' + str(n)) for s in SCENARIOS for n in SEEDS}
    actual = {p.relative_to(root) for p in root.glob('*/*') if p.is_dir()}
    require(actual == expected, f'Input coverage mismatch: missing={expected-actual}, extra={actual-expected}')
    found = {}
    for rel in sorted(expected):
        path = root / rel
        for filename in ('config.json', 'payments.csv', 'inflows.csv', 'manifest.json'):
            require((path / filename).is_file(), f'Missing input: {path / filename}')
        c = json.loads((path / 'config.json').read_text(encoding='utf-8'))
        require(c['scenario_id'] == rel.parts[0] and int(c['seed']) == int(rel.parts[1].split('_')[1]), f'Mislabelled input: {path}')
        require(c['dataset_id'] not in found, f'Duplicate dataset: {path}')
        found[c['dataset_id']] = path
    return found


def audit_trace(payments, inflows, config, events, balances, trades, summary):
    """Independently replay every cash-changing event and check every snapshot."""
    require(summary.get('using_fallback_module5') is False, 'Module 5 fallback used')
    if summary['strategy_id'] in ('S2', 'S4'):
        require(summary.get('using_fallback_module4') is False, 'Module 4 fallback used')
    require(events and len(events) == len(balances), 'Missing/unpaired events and balances')
    pmap = {p['payment_id']: p for p in payments}
    fmap = {f['inflow_id']: f for f in inflows}
    tmap = {t['fx_id']: t for t in trades}
    require(len(pmap) == len(payments) and len(tmap) == len(trades), 'Duplicate payment or FX id')
    cash, hkd = D(str(config['initial_rmb_balance'])), D(str(config['initial_hkd_balance']))
    reserve, buffer = D(str(config['rmb_reserve'])), D(str(config.get('hkd_liquidity_buffer', 0)))
    locked, committed = D(0), D(0)
    active, settled, pending, completed, credited = set(), set(), set(), set(), set()
    last_time = -1
    for seq, (e, b) in enumerate(zip(events, balances)):
        require(int(e['event_seq']) == seq == int(b['event_seq']), 'Invalid event sequence')
        now = int(e['time'])
        require(now >= last_time and now == int(b['time']), 'Invalid event time')
        require(e['run_id'] == b['run_id'] == summary['run_id'], 'Wrong run identity')
        last_time = now
        kind, pid, fid = e['event_type'], e['payment_id'], e['fx_id']
        if kind == 'INFLOW_ARRIVAL':
            iid = dict(v.split('=', 1) for v in e['reason'].split(';'))['inflow_id']
            require(iid not in credited and int(fmap[iid]['arrival_time']) == now, 'Invalid inflow credit')
            credited.add(iid)
            cash += D(str(fmap[iid]['amount_rmb']))
        elif kind == 'PAYMENT_SUBMITTED':
            amount = D(str(pmap[pid]['amount_rmb']))
            require(pid not in active | settled and int(pmap[pid]['arrival_time']) <= now, 'Duplicate/premature submission')
            require(str(pmap[pid].get('eligible', True)).lower() == 'true', 'Ineligible submission')
            require(amount <= max(D(0), cash-locked-reserve), 'Submission exceeds available RMB')
            active.add(pid)
            locked += amount
        elif kind in ('PAYMENT_SETTLED', 'PAYMENT_CONFIRM_FAILED'):
            require(pid in active, 'Confirmation without submission')
            active.remove(pid)
            amount = D(str(pmap[pid]['amount_rmb']))
            locked -= amount
            if kind == 'PAYMENT_SETTLED':
                require(pid not in settled, 'Repeated settlement')
                settled.add(pid)
                cash -= amount
        elif kind == 'FX_INITIATED':
            t = tmap[fid]
            require(fid not in pending | completed and int(t['initiated_at']) == now, 'Duplicate FX initiation')
            cost = D(t['hkd_principal']) + D(t['hkd_fee'])
            require(cost <= max(D(0), hkd-committed-buffer), 'FX exceeds available HKD')
            pending.add(fid)
            committed += cost
        elif kind == 'FX_COMPLETED':
            t = tmap[fid]
            require(fid in pending and now == int(t['completed_at']) ==
                    int(t['initiated_at']) + int(config['fx_execution_delay_sec']), 'Invalid FX completion')
            pending.remove(fid)
            completed.add(fid)
            cost = D(t['hkd_principal']) + D(t['hkd_fee'])
            committed -= cost
            hkd -= cost
            cash += D(t['topup_rmb'])
        expected = dict(rmb_total=cash, rmb_reserved=reserve, rmb_locked=locked,
                        rmb_available=max(D(0), cash-locked-reserve), hkd_total=hkd,
                        hkd_committed=committed, hkd_available=max(D(0), hkd-committed-buffer))
        for field, value in expected.items():
            require(D(b[field]) == value, f'{summary["run_id"]} event {seq}: incorrect {field}')
        require(locked >= 0 and committed >= 0, 'Negative commitment')
    require(events[-1]['event_type'] == 'SIMULATION_END' and last_time == int(summary['observation_end_sec']), 'Incomplete observation')
    require(settled == {p['payment_id'] for p in payments if p['final_status'] == 'SETTLED'}, 'Settlement table mismatch')
    require(active == {p['payment_id'] for p in payments if p['final_status'] == 'PENDING'}, 'Pending payment mismatch')
    require(pending == {t['fx_id'] for t in trades if t['status'] == 'PENDING'}, 'Pending FX mismatch')
    require(completed == {t['fx_id'] for t in trades if t['status'] == 'COMPLETED'}, 'Completed FX mismatch')
    for key, value in [('rmb_total_end', cash), ('hkd_total_end', hkd), ('rmb_locked_end', locked), ('hkd_committed_end', committed)]:
        require(D(summary[key]) == value, f'Incorrect summary: {key}')


def audit_saved(root):
    root = Path(root)
    inputs = pilot_inputs(root / 'vendor/pilot')
    expected = {f'{name}_{s}' for name in inputs for s in STRATEGIES}
    folder = root / 'evidence/pilot_runs'
    actual = {p.name for p in folder.iterdir() if p.is_dir()} if folder.exists() else set()
    require(actual == expected, f'Expected {len(expected)} runs; missing={expected-actual}, extra={actual-expected}')
    table = read_rows(root / 'evidence/pilot_comparison.csv')
    keys = [(r['scenario'], int(r['seed']), r['strategy']) for r in table]
    require(len(keys) == len(set(keys)) == len(expected), 'Duplicate/missing comparison rows')
    index = dict(zip(keys, table))
    from m3engine.io import load_dataset
    for name, source in inputs.items():
        load_dataset(source)
        c = json.loads((source / 'config.json').read_text(encoding='utf-8'))
        for strategy in STRATEGIES:
            out = folder / f'{name}_{strategy}'
            for filename in FILES:
                require((out / filename).is_file(), f'Missing result: {out / filename}')
            summary = json.loads((out / 'run_summary.json').read_text(encoding='utf-8'))
            require(summary['dataset_id'] == name and summary['run_id'] == out.name and
                    summary['strategy_id'] == strategy and summary['scenario_id'] == c['scenario_id'] and
                    int(summary['seed']) == int(c['seed']), 'Saved result identity mismatch')
            row = index.get((c['scenario_id'], int(c['seed']), strategy))
            require(row is not None and row['input_sha256'] == input_digest(source), 'Comparison input mismatch')
            require(row['fallback5'] == 'False' and (strategy not in ('S2', 'S4') or row['fallback4'] == 'False'), 'Comparison fallback used')
            ps = read_rows(out / 'payment_results.csv')
            original = read_rows(source / 'payments.csv')
            require(len(ps) == len(original) and {p['payment_id'] for p in ps} == {p['payment_id'] for p in original}, 'Missing source payments')
            originals = {p['payment_id']: p for p in original}
            for p in ps:
                for field in ('arrival_time', 'amount_rmb', 'deadline_time'):
                    require(D(p[field]) == D(originals[p['payment_id']][field]), 'Altered source payment')
                p['eligible'] = originals[p['payment_id']]['eligible']
            for field in ('settled', 'ineligible'):
                require(int(row[field]) == summary[field], f'Comparison mismatch: {field}')
            require(int(row['unfinished']) == summary['queued'] + summary['pending'], 'Unfinished count mismatch')
            require(int(row['fx']) == summary['fx_initiated'] and D(row['fx_cost']) == D(summary['fx_cost_rmb']), 'FX comparison mismatch')
            audit_trace(ps, read_rows(source / 'inflows.csv'), c, read_rows(out / 'events.csv'),
                        read_rows(out / 'balances.csv'), read_rows(out / 'fx_trades.csv'), summary)
    return len(expected)
