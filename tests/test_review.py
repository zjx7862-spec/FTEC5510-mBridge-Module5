"""Regression cases for timing, semantic logging, scheduling and fail-closed audits."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_funding import C, Q, S, F, decide, Simulation, Payment, Inflow
from validation import audit_trace, audit_saved, pilot_inputs, FILES, STRATEGIES


def evidence(decision):
    return json.loads(decision['reason'].split(';evidence=', 1)[1])


class TimingTests(unittest.TestCase):
    def call(self, trades, inflows=(), now=0, deadline=30):
        return decide([dict(Q[0], deadline_time=deadline)], dict(S, t=now, pending_fx=trades),
                      list(inflows), C, 'wait_or_topup')

    def test_full_timely(self):
        d = self.call([dict(topup_rmb=100, expected_completion_time=10)])
        self.assertEqual(d['action'], 'NO_ACTION')
        self.assertIs(evidence(d)['deadline_risk'], False)

    def test_full_late(self):
        d = self.call([dict(topup_rmb=100, expected_completion_time=100)])
        self.assertEqual(d['topup_rmb'], 0)
        self.assertIs(evidence(d)['deadline_risk'], True)

    def test_multiple_sufficient_time(self):
        d = self.call([dict(topup_rmb=40, expected_completion_time=10),
                       dict(topup_rmb=60, expected_completion_time=26)])
        self.assertEqual(evidence(d)['pending_sufficient_at'], 26)
        self.assertIs(evidence(d)['deadline_risk'], False)

    def test_part_timely_full_late(self):
        d = self.call([dict(topup_rmb=40, expected_completion_time=10),
                       dict(topup_rmb=60, expected_completion_time=27)])
        self.assertIs(evidence(d)['deadline_risk'], True)

    def test_missing_time(self):
        for trade in [dict(topup_rmb=100), dict(topup_rmb=100, expected_completion_time=None)]:
            d = self.call([trade])
            self.assertIs(evidence(d)['deadline_risk'], None)
            self.assertTrue(evidence(d)['pending_timing_unknown'])
            self.assertEqual(d['topup_rmb'], 0)

    def test_unknown_time_not_needed_for_coverage(self):
        d = self.call([dict(topup_rmb=100, expected_completion_time=10), dict(topup_rmb=1)])
        self.assertIs(evidence(d)['deadline_risk'], False)

    def test_partial_pending_with_notice(self):
        d = self.call([dict(topup_rmb=40, expected_completion_time=10)],
                      [dict(F[0], amount_rmb=60, arrival_time=20)])
        self.assertEqual(d['action'], 'WAIT')
        self.assertEqual(evidence(d)['sufficient_at'], 20)

    def test_partial_pending_late_new_fx_is_not_enough_alone(self):
        d = self.call([dict(topup_rmb=40, expected_completion_time=100)])
        self.assertEqual(d['topup_rmb'], 60)
        self.assertIs(evidence(d)['deadline_risk'], True)

    def test_partial_pending_unknown_new_fx(self):
        d = self.call([dict(topup_rmb=40)])
        self.assertEqual(d['topup_rmb'], 60)
        self.assertIs(evidence(d)['deadline_risk'], None)

    def test_notice_is_not_counted_twice_in_fx_amount(self):
        d = self.call([dict(topup_rmb=40, expected_completion_time=10)],
                      [dict(F[0], amount_rmb=60, arrival_time=100)])
        self.assertEqual(d['action'], 'TOP_UP')
        self.assertEqual(d['topup_rmb'], 60)

    def test_pending_evidence_does_not_embed_old_reasons(self):
        d = self.call([dict(topup_rmb=40, expected_completion_time=10,
                            reason='previous evidence' * 10000)])
        self.assertLess(len(d['reason']), 2000)
        self.assertNotIn('previous evidence', d['reason'])


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation([Payment('A', 0, 100, 'NORMAL', 30),
                               Payment('B', 0, 100, 'NORMAL', 30)], [], C, 'S3')

    def emit(self, at=0, pid='A', action='NO_ACTION', code='test', **values):
        self.sim.now = at
        self.sim.state.t = at
        reason = code + ';evidence=' + json.dumps(dict(t=at, **values), sort_keys=True)
        self.sim._log_decision(self.sim.by_id[pid], action, reason)

    def test_timestamp_only_deduplicated(self):
        self.emit(at=0, gap=100)
        self.emit(at=1, gap=100)
        self.assertEqual(len(self.sim.events), 1)

    def test_target_switch_and_return(self):
        for pid in ['A', 'B', 'A']:
            self.emit(pid=pid)
        self.assertEqual(len(self.sim.events), 3)

    def test_gap_and_topup_change(self):
        self.emit(gap=100, topup_rmb=100)
        self.emit(gap=99, topup_rmb=99)
        self.assertEqual(len(self.sim.events), 2)

    def test_risk_change_logged(self):
        self.emit(deadline_risk=False)
        self.emit(at=1, deadline_risk=True)
        self.assertEqual(len(self.sim.events), 2)

    def test_constraint_change_logged(self):
        self.emit(code='insufficient_hkd')
        self.emit(code='exceeds_counterparty_capacity')
        self.assertEqual(len(self.sim.events), 2)

    def test_action_change_logged(self):
        self.emit(action='WAIT')
        self.emit(action='TOP_UP')
        self.assertEqual(len(self.sim.events), 2)

    def test_real_fx_risk_transition(self):
        for now in [0, 1, 24]:
            d = decide(Q, dict(S, t=now), [], C, 'wait_or_topup')
            self.sim.now = now
            self.sim._log_decision(self.sim.by_id['A'], d['action'], d['reason'])
        self.assertEqual(len(self.sim.events), 2)


class IntegrationTests(unittest.TestCase):
    def test_s0_and_s1(self):
        ps = [Payment('A', 0, 100, 'NORMAL', 30), Payment('B', 0, 50, 'NORMAL', 30)]
        results = [Simulation(ps, [], dict(C, initial_rmb_balance=50), s).run() for s in ('S0', 'S1')]
        self.assertGreater(results[0].payments[1]['submit_time'], 0)
        self.assertEqual(results[1].payments[1]['submit_time'], 0)
        for r in results:
            self.assertFalse(r.summary['using_fallback_module5'])
            self.assertFalse(any(e['action'] == 'WAIT' for e in r.events))

    def test_engine_hides_unknown_future(self):
        def capture(inflows):
            seen = []
            def spy(q, s, f, c, mode):
                seen.append((s['t'], copy.deepcopy(f)))
                return decide(q, s, f, c, mode)
            Simulation([Payment('A', 1, 100, 'NORMAL', 30)], inflows, C, 'S3', decide_fn=spy).run()
            return [(t, f) for t, f in seen if t < 10]
        self.assertEqual(capture([]), capture([Inflow('hidden', 20, 100, 10)]))

    def test_review_scheduled_and_bounded(self):
        seen = []
        def wait(q, s, f, c, mode):
            seen.append(s['t'])
            return dict(action='WAIT', reason='probe', next_check_time=s['t']+1)
        Simulation([Payment('A', 1, 100, 'NORMAL', 30)], [], C, 'S3', decide_fn=wait).run()
        self.assertIn(2, seen)
        self.assertLessEqual(len(seen), 102)
        self.assertTrue(all(1 <= t <= 100 for t in seen))

    def test_every_event_replay_and_corruption(self):
        inflows = [Inflow('F', 10, 100, 0)]
        r = Simulation([Payment('A', 1, 100, 'NORMAL', 30)], inflows, C, 'S3').run()
        fs = [dict(inflow_id='F', arrival_time=10, amount_rmb=100)]
        audit_trace(r.payments, fs, C, r.events, r.balances, r.fx_trades, r.summary)
        bad = copy.deepcopy(r.balances)
        bad[1]['rmb_total'] = '1.00'
        with self.assertRaisesRegex(ValueError, 'incorrect rmb_total'):
            audit_trace(r.payments, fs, C, r.events, bad, r.fx_trades, r.summary)
        with self.assertRaisesRegex(ValueError, 'fallback'):
            audit_trace(r.payments, fs, C, r.events, r.balances, r.fx_trades,
                        dict(r.summary, using_fallback_module5=True))

    def test_confirmation_failure_release_replay(self):
        c = dict(C, initial_rmb_balance=100, payment_confirmation_fail_prob=1)
        r = Simulation([Payment('A', 1, 100, 'NORMAL', 30)], [], c, 'S3').run()
        self.assertTrue(any(e['event_type'] == 'PAYMENT_CONFIRM_FAILED' for e in r.events))
        audit_trace(r.payments, [], c, r.events, r.balances, r.fx_trades, r.summary)


class CoverageTests(unittest.TestCase):
    def test_missing_input_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Input coverage'):
                pilot_inputs(Path(tmp))

    def test_zero_or_missing_strategy_results(self):
        for present in [(), ('S1', 'S2', 'S3')]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for s in present:
                    (root/'evidence/pilot_runs'/f'dataset_{s}').mkdir(parents=True)
                with patch('validation.pilot_inputs', return_value={'dataset': root/'source'}):
                    with self.assertRaisesRegex(ValueError, 'Expected 4 runs'):
                        audit_saved(root)

    def test_missing_result_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source'
            source.mkdir()
            (source/'config.json').write_text(json.dumps(dict(scenario_id='baseline', seed=1001)))
            for s in STRATEGIES:
                (root/'evidence/pilot_runs'/f'dataset_{s}').mkdir(parents=True)
            table = [dict(scenario='baseline', seed='1001', strategy=s) for s in STRATEGIES]
            with patch('validation.pilot_inputs', return_value={'dataset': source}), \
                 patch('validation.read_rows', return_value=table), \
                 patch('m3engine.io.load_dataset'):
                with self.assertRaisesRegex(ValueError, 'Missing result'):
                    audit_saved(root)


if __name__ == '__main__':
    unittest.main()
