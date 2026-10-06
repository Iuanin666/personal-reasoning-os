from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import personal_os as pos

def rows(path):
 return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def main():
 ap=argparse.ArgumentParser(description='Run the synthetic public retrieval evaluation.')
 ap.add_argument('--config',default=str(ROOT/'work/demo-vault/PersonalOS/.personal-os/config.yaml'))
 ap.add_argument('--formal-holdout',action='store_true',help='Load the separated holdout answer key for a formal run.')
 ap.add_argument('--output')
 a=ap.parse_args()
 cases=rows(ROOT/'evaluation/dev.jsonl')
 split='dev'
 if a.formal_holdout:
  queries={x['id']:x for x in rows(ROOT/'evaluation/holdout.queries.jsonl')}
  answers={x['id']:x for x in rows(ROOT/'evaluation/holdout.answers.jsonl')}
  cases=[queries[k]|answers[k] for k in queries];split='holdout'
 store=pos.Store(a.config);details=[];recall5=[];recall10=[];rr=[];clean=[];silence=[];lat=[]
 for case in cases:
  start=time.perf_counter();diag=store.search_diagnostic(case['query'],top_k=10,retrieval_profile='optimized_v1');lat.append((time.perf_counter()-start)*1000)
  ids=[]
  for row in diag['candidates']:
   if row['note_id'] not in ids:ids.append(row['note_id'])
  expected=case.get('expected_note_ids',[]);forbidden=set(case.get('forbidden_or_confusing_note_ids',[]))
  if expected:
   recall5.append(sum(x in ids[:5] for x in expected)/len(expected));recall10.append(sum(x in ids[:10] for x in expected)/len(expected))
   ranks=[ids.index(x)+1 for x in expected if x in ids];rr.append(1/min(ranks) if ranks else 0)
  if forbidden:clean.append(not bool(forbidden&set(ids[:5])))
  if case.get('expected_abstain'):silence.append(diag['status']=='no_relevant_evidence')
  details.append({'id':case['id'],'top10':ids[:10],'evidence_status':diag['status']})
 avg=lambda xs:round(sum(xs)/len(xs),4) if xs else None
 result={'split':split,'cases':len(cases),'recall_at_5':avg(recall5),'recall_at_10':avg(recall10),'mrr':avg(rr),'hard_negative_clean_at_5':avg(clean),'no_relevant_evidence_accuracy':avg(silence),'median_latency_ms':round(sorted(lat)[len(lat)//2],2),'details':details}
 text=json.dumps(result,ensure_ascii=False,indent=2);print(text)
 if a.output:Path(a.output).write_text(text+'\n',encoding='utf-8')
 return 0
if __name__=='__main__':raise SystemExit(main())
