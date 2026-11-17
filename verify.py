"""Reproduce hand cases and paired pilot comparisons; not Module 6 metrics."""
import sys,json,csv,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'vendor'),str(ROOT/'tests')]
from m3engine import load_dataset,run_dataset,write_outputs
from test_funding import C
from m3engine.engine import Simulation
from m3engine.models import Payment,Inflow

from validation import pilot_inputs, audit_trace, STRATEGIES, require


def audit(r, config, inflows):
    audit_trace(r.payments, [dict(inflow_id=f.inflow_id, arrival_time=f.arrival_time,
                amount_rmb=f.amount_rmb) for f in inflows], config, r.events,
                r.balances, r.fx_trades, r.summary)

if __name__=='__main__':
    sources = pilot_inputs(ROOT/'vendor/pilot')
    out=ROOT/'evidence'
    for name,inflows,c in [('wait',[Inflow('F',10,100,0)],C),('fx',[],C),('infeasible',[],dict(C,initial_hkd_balance=0))]:
        r_config=c
        r=Simulation([Payment('A',1,100,'NORMAL',30)],inflows,c,'S3').run();audit(r,c,inflows)
        write_outputs(r,out/name)
        (out/name/'run_summary.json').write_text(json.dumps(r.summary,indent=2),encoding='utf-8')
    rows=[]
    for path in sorted(sources.values()):
        ds=load_dataset(path);r_config=ds.config
        digest=hashlib.sha256(b''.join((path/f).read_bytes() for f in ['config.json','payments.csv','inflows.csv'])).hexdigest()
        for strategy in STRATEGIES:
            r=run_dataset(ds,strategy);audit(r,ds.config,ds.inflows)
            run_out=out/'pilot_runs'/r.run_id
            write_outputs(r,run_out)
            (run_out/'run_summary.json').write_text(json.dumps(r.summary,indent=2),encoding='utf-8')
            rows.append(dict(scenario=ds.config['scenario_id'],seed=ds.config['seed'],strategy=strategy,input_sha256=digest,settled=r.summary['settled'],unfinished=r.summary['queued']+r.summary['pending'],ineligible=r.summary['ineligible'],fx=r.summary['fx_initiated'],fx_cost=r.summary['fx_cost_rmb'],funding_decisions=sum(e['event_type']=='FUNDING_DECISION' for e in r.events),fallback4=r.summary['using_fallback_module4'],fallback5=r.summary['using_fallback_module5']))
    require(len(rows) == 84, 'Incomplete pilot matrix')
    with (out/'pilot_comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print(f'Hand cases: 3; pilot runs: {len(rows)}; audits passed. See evidence/pilot_comparison.csv')
