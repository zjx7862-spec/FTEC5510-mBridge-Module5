"""Deliberately corrupt a small saved matrix to check failure paths."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_funding import C, Payment, Simulation
from m3engine.io import write_outputs
from validation import audit_saved, input_digest, read_rows, STRATEGIES


def write_table(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class SavedAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'
        self.source.mkdir()
        c = dict(C, dataset_id='small', scenario_id='baseline', seed=1001)
        (self.source/'config.json').write_text(json.dumps(c))
        write_table(self.source/'payments.csv', [dict(payment_id='A', arrival_time=1,
                    amount_rmb=100, priority='NORMAL', deadline_time=30, eligible='true')])
        (self.source/'inflows.csv').write_text('inflow_id,arrival_time,amount_rmb,notice_time\n')
        self.rows = []
        for strategy in STRATEGIES:
            r = Simulation([Payment('A', 1, 100, 'NORMAL', 30)], [], c, strategy).run()
            out = self.root/'evidence/pilot_runs'/r.run_id
            write_outputs(r, out)
            (out/'run_summary.json').write_text(json.dumps(r.summary))
            self.rows.append(dict(scenario='baseline', seed=1001, strategy=strategy,
                input_sha256=input_digest(self.source), settled=1, unfinished=0,
                ineligible=0, fx=r.summary['fx_initiated'], fx_cost=r.summary['fx_cost_rmb'],
                fallback4=False, fallback5=False))
        self.table = self.root/'evidence/pilot_comparison.csv'
        write_table(self.table, self.rows)
        self.addCleanup(patch.stopall)
        patch('validation.pilot_inputs', return_value={'small': self.source}).start()
        patch('m3engine.io.load_dataset').start()  # These tests target saved outputs, not manifests.

    def test_valid_saved_matrix(self):
        self.assertEqual(audit_saved(self.root), 4)

    def test_wrong_input_digest(self):
        self.rows[0]['input_sha256'] = 'wrong'
        write_table(self.table, self.rows)
        with self.assertRaisesRegex(ValueError, 'input mismatch'):
            audit_saved(self.root)

    def test_fallback_in_summary(self):
        p = self.root/'evidence/pilot_runs/small_S1/run_summary.json'
        c = json.loads(p.read_text())
        c['using_fallback_module5'] = True
        p.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError, 'fallback'):
            audit_saved(self.root)

    def test_wrong_output_identity(self):
        p = self.root/'evidence/pilot_runs/small_S1/run_summary.json'
        c = json.loads(p.read_text())
        c['dataset_id'] = 'other_source'
        p.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            audit_saved(self.root)

    def test_duplicate_comparison_rows(self):
        self.rows[-1] = dict(self.rows[0])
        write_table(self.table, self.rows)
        with self.assertRaisesRegex(ValueError, 'comparison rows'):
            audit_saved(self.root)

    def test_corrupt_intermediate_balance(self):
        p = self.root/'evidence/pilot_runs/small_S1/balances.csv'
        rows = read_rows(p)
        rows[1]['hkd_total'] = '99999'
        write_table(p, rows)
        with self.assertRaisesRegex(ValueError, 'incorrect hkd_total'):
            audit_saved(self.root)
