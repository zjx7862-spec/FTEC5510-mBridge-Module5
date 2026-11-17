import sys, json, copy, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from module5_funding import decide_funding as decide
from m3engine.engine import Simulation
from m3engine.models import Payment, Inflow
C=dict(simulation_window_sec=100,initial_rmb_balance=0,rmb_reserve=0,initial_hkd_balance=1000,
       fx_rate=1,fx_spread_bps=0,fx_fee_fixed_hkd=1,fx_execution_delay_sec=5,
       fx_topup_min_rmb=1,fx_topup_max_rmb=1000,fx_counterparty_capacity_rmb=1000,
       fx_safety_buffer_sec=2,funding_review_interval_sec=3,payment_confirmation_delay_sec=2)
Q=[dict(payment_id='A',arrival_time=0,amount_rmb=100,priority='NORMAL',deadline_time=30)]
S=dict(t=0,rmb_available=0,hkd_available=1000,cpty_remaining=1000,pending_fx=[])
F=[dict(inflow_id='F',arrival_time=10,amount_rmb=100,notice_time=0)]
class FundingTests(unittest.TestCase):
    def call(self,c=None,s=None,f=None,q=None,mode='wait_or_topup'):
        return decide(Q if q is None else q,S if s is None else s,F if f is None else f,C if c is None else c,mode)
    def test_wait(self): self.assertEqual(self.call()['action'],'WAIT')
    def test_cumulative(self):
        self.assertEqual(self.call(f=[dict(F[0],amount_rmb=40),dict(F[0],arrival_time=15,amount_rmb=60)])['action'],'WAIT')
    def test_late_and_insufficient(self):
        for f in ([dict(F[0],arrival_time=29)],[dict(F[0],amount_rmb=99)],[]):
            self.assertEqual(self.call(f=f)['action'],'TOP_UP')
    def test_constraints(self):
        for c,s in [(C,dict(S,hkd_available=100)),(dict(C,fx_counterparty_capacity_rmb=99),S),(dict(C,fx_topup_max_rmb=99),S),(dict(C,fx_quote_valid=False),S),(dict(C,engine_parameters={'fx_counterparty_capacity_mode':'cumulative'}),dict(S,cpty_remaining=50))]:
            self.assertEqual(self.call(c=c,s=s,f=[])['action'],'NO_ACTION')
    def test_pending(self):
        for amount, action, need in [(100,'NO_ACTION',0),(40,'TOP_UP',60)]:
            d=self.call(s=dict(S,pending_fx=[dict(topup_rmb=amount,expected_completion_time=10)]),f=[])
            self.assertEqual(d['action'],action);self.assertEqual(d['topup_rmb'],need)
    def test_unknown(self): self.assertEqual(self.call(f=[dict(F[0],notice_time=1)]),self.call(f=[]))
    def test_boundary(self):
        self.assertEqual(self.call(f=[dict(F[0],arrival_time=26)])['action'],'WAIT')
        self.assertEqual(self.call(f=[dict(F[0],arrival_time=27)])['action'],'TOP_UP')
        self.assertIn('true',self.call(q=[dict(Q[0],deadline_time=-1)],f=[])['reason'])
    def test_immediate(self): self.assertEqual(self.call(mode='immediate')['action'],'TOP_UP')
    def test_pure(self):
        before=copy.deepcopy((Q,S,F,C)); self.assertEqual(self.call(),self.call());self.assertEqual(before,(Q,S,F,C))
    def test_nonfunding(self): self.assertEqual(self.call(q=[dict(Q[0],eligible=False)])['action'],'NO_ACTION')
    def test_minimum(self): self.assertEqual(self.call(c=dict(C,fx_topup_min_rmb=200),f=[])['topup_rmb'],200)
    def run_case(self,inflows=(),config=None,strategy='S3',payments=None):
        return Simulation(payments or [Payment('A',1,100,'NORMAL',30)],list(inflows),config or C,strategy).run()
    def test_e2e_wait(self):
        r=self.run_case([Inflow('F',10,100,0)])
        self.assertEqual(r.payments[0]['settle_time'],12);self.assertEqual(r.summary['fx_initiated'],0)
        self.assertTrue(any(e['action']=='WAIT' for e in r.events))
    def test_e2e_fx(self):
        r=self.run_case();self.assertEqual(r.summary['fx_initiated'],1);self.assertEqual(r.payments[0]['settle_time'],8)
        self.assertEqual(r.summary['hkd_total_end'],'899.00'); self.assertEqual(r.summary['hkd_committed_end'],'0.00')
        for b in r.balances:
            if b['time']<6:self.assertEqual(b['rmb_total'],'0.00')
        self.assertEqual(sum(e['event_type']=='PAYMENT_SETTLED' for e in r.events),1)
    def test_e2e_infeasible(self):
        r=self.run_case(config=dict(C,initial_hkd_balance=0));self.assertEqual(r.payments[0]['final_status'],'QUEUED')
    def test_ranking_and_loading(self):
        ps=[Payment('A',0,100,'NORMAL',100),Payment('B',0,150,'URGENT',20)]
        s3=Simulation(ps,[],C,'S3');s4=Simulation(ps,[],C,'S4')
        for s in (s3,s4):
            for p in s.payments:p.status='QUEUED'
        self.assertEqual(s3._ordered_queue()[0].payment_id,'A');self.assertEqual(s4._ordered_queue()[0].payment_id,'B')
        self.assertEqual(s4.using_fallback,(False,False))
    def test_skipping(self):
        r=self.run_case(config=dict(C,initial_rmb_balance=50),payments=[Payment('A',0,100,'NORMAL',30),Payment('B',0,50,'NORMAL',30)])
        self.assertEqual(r.payments[1]['submit_time'],0)
    def test_partial_pending_execution(self):
        sim=Simulation([Payment('A',0,100,'NORMAL',30)],[],C,'S3')
        sim.payments[0].status='QUEUED'
        sim._execute_top_up(sim.payments[0],40)
        sim._funding_decision(sim.payments[0])
        self.assertEqual(sum(f['topup_rmb'] for f in sim.state.pending_fx),100)
        sim._funding_decision(sim.payments[0])
        self.assertEqual(len(sim.state.pending_fx),2)
    def test_s4_funding_target(self):
        ps=[Payment('A',0,100,'NORMAL',100),Payment('B',0,150,'URGENT',20)]
        targets=[]
        for strategy in ('S3','S4'):
            sim=Simulation(ps,[],C,strategy)
            for p in sim.payments:p.status='QUEUED'
            sim._review()
            targets.append(sim.state.pending_fx[0]['target_payment_id'])
        self.assertEqual(targets,['A','B'])
if __name__=='__main__':unittest.main()
