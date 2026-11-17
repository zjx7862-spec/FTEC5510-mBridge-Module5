"""Pure funding advice; queue must be in engine strategy order (contract v1.1)."""
import json
from decimal import Decimal, ROUND_HALF_UP

def money(x):
    return Decimal(str(x)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def decide_funding(queue, state, known_inflows, config, mode):
    if mode not in ('immediate', 'wait_or_topup'):
        raise ValueError('unsupported funding mode')
    now = int(state['t'])
    params = dict(config)
    params.update(config.get('engine_parameters', {}))
    interval = max(1, int(config.get('funding_review_interval_sec', 60)))
    nxt = now + interval
    evidence = {'t': now, 'forecast_source': 'notified_only'}
    def result(action, reason, target=None, amount=0):
        return dict(action=action, target_payment_id=target, topup_rmb=money(amount),
                    reason=reason + ';evidence=' + json.dumps(evidence, default=str, sort_keys=True),
                    next_check_time=nxt)
    eligible = [q for q in queue if q.get('eligible', True)]
    available = money(state['rmb_available'])
    if not eligible or any(money(q['amount_rmb']) <= available for q in eligible):
        return result('NO_ACTION', 'no_funding_trigger')
    target = eligible[0]
    pid = target['payment_id']
    gap = money(target['amount_rmb']) - available
    pending = sum((money(f['topup_rmb']) for f in state.get('pending_fx', [])), money(0))
    confirm = int(params.get('payment_confirmation_delay_sec', 10))
    margin = int(config.get('fx_safety_buffer_sec', 0))
    deadline = int(target['deadline_time'])
    evidence.update(gap=gap, pending_rmb=pending, deadline=deadline,
                    confirmation_sec=confirm, safety_sec=margin)
    # Missing completion times are uncertainty, not immediately usable cash.
    pending_credits = [(int(f['expected_completion_time']), money(f['topup_rmb']))
                       for f in state.get('pending_fx', [])
                       if f.get('expected_completion_time') is not None]
    evidence['pending_fx'] = [{k: f[k] for k in ('fx_id', 'topup_rmb', 'expected_completion_time') if k in f}
                              for f in state.get('pending_fx', [])]
    evidence['pending_timing_unknown'] = any(
        f.get('expected_completion_time') is None for f in state.get('pending_fx', []))

    def sufficient_time(credits):
        total = money(0)
        for at, amount in sorted(credits):
            total += amount
            if total >= gap:
                return max(now, at)
        return None

    def deadline_risk(at):
        return None if at is None else at + confirm + margin > deadline

    pending_at = sufficient_time(pending_credits)
    evidence['pending_sufficient_at'] = pending_at
    if pending >= gap:
        evidence.update(sufficient_at=pending_at, deadline_risk=deadline_risk(pending_at))
        if pending_at is not None:
            nxt = min(nxt, max(now + 1, pending_at))
        return result('NO_ACTION', 'pending_fx_covers_gap', pid)

    # Only revealed notices are accepted. The engine enforces its lookahead window.
    notified = [f for f in known_inflows
                if f.get('notice_time', now) is not None
                and f.get('notice_time', now) <= now
                and int(f['arrival_time']) >= now]
    credits = pending_credits + [(int(f['arrival_time']), money(f['amount_rmb']))
                                 for f in notified]
    evidence['notified_inflows'] = notified
    sufficient = sufficient_time(credits)
    evidence['sufficient_at'] = sufficient
    if mode == 'wait_or_topup' and sufficient is not None and not deadline_risk(sufficient):
        evidence['deadline_risk'] = False
        nxt = min(nxt, max(now + 1, sufficient))
        return result('WAIT', 'notified_funding_timely', pid)
    need = max(money(config['fx_topup_min_rmb']), gap + money(params.get('fx_buffer_rmb', 0)) - pending)
    rate = Decimal(str(config['fx_rate'])) * (1 - Decimal(str(config.get('fx_spread_bps', 0)))/10000)
    # The new trade alone may not cover the gap: include earlier pending credits
    # only at their completion times. Unknown times keep the risk indeterminate.
    fx_at = sufficient_time(pending_credits + [(now + int(config['fx_execution_delay_sec']), need)])
    evidence.update(topup_rmb=need, fx_execution_sec=int(config['fx_execution_delay_sec']),
                    deadline_risk=deadline_risk(fx_at))
    reason = None
    if not config.get('fx_quote_valid', True) or rate <= 0:
        reason = 'invalid_quote'
    elif need > money(config['fx_topup_max_rmb']):
        reason = 'exceeds_fx_topup_max_rmb'
    elif need > money(state['cpty_remaining'] if params.get('fx_counterparty_capacity_mode', 'per_trade') == 'cumulative' else config['fx_counterparty_capacity_rmb']):
        reason = 'exceeds_counterparty_capacity'
    elif money(need/rate) + money(config.get('fx_fee_fixed_hkd', 0)) > money(state['hkd_available']):
        reason = 'insufficient_hkd'
    return result('NO_ACTION' if reason else 'TOP_UP', reason or 'executable_fx', pid, 0 if reason else need)
