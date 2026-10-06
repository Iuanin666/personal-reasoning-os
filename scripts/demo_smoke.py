from __future__ import annotations
import json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'src'))
import personal_os as pos, ingest, context_engine, analyze, profile_evolution

def main():
 vault=ROOT/'work/demo-vault'
 if vault.exists():shutil.rmtree(vault)
 subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/create-demo.ps1'),'-Destination',str(vault)],check=True,capture_output=True,text=True)
 config=vault/'PersonalOS/.personal-os/config.yaml'
 store=pos.Store(config);started=time.perf_counter()
 rebuilt=store.index(rebuild=True)
 decision=store.search('Why did Lin pilot one garden before expanding?',top_k=5,retrieval_profile='optimized_v1')
 if not any(x['note_id']=='DEC-2030-0001' for x in decision):raise AssertionError('decision retrieval failed')
 reflected=store.reflect({'mode':'current','import_id':'IMP-DEMO-SMOKE-001','material':{'material_id':'MAT-DEMO-SMOKE-001','source_type':'current_conversation','source_ref':'synthetic smoke'},'experience':{'title':'Ran a fictional volunteer check-in','facts':'Lin ran a synthetic ten-minute volunteer check-in.','event_date':'2030-07-01','source':'synthetic demo'}})
 packet={'input':{'kind':'text','value':'A fictional third-party note says small reversible trials can expose schedule constraints.','name':'synthetic-summary.txt'},'knowledge':{'knowledge_type':'article','source_type':'third_party_summary','source_scope':'excerpt','tags':['synthetic-demo']}}
 plan=ingest.make_plan(config,packet,ROOT/'tools/defuddle/node_modules/.bin/defuddle.cmd',ROOT/'.venv-ingest/Scripts/python.exe')
 applied=ingest.apply_plan(Path(plan['plan_path']))
 store=pos.Store(config)
 indexed=store.index();validated=store.validate()
 engine=context_engine.ContextEngine(config)
 try:pack=engine.build('Why did Lin pilot one garden before expanding?','history','self')
 finally:engine.close()
 analysis=analyze.make_plan(config,'Analyze whether Lin should expand the fictional workshop, then challenge the assumptions.')
 review=profile_evolution.ProfileEvolution(config)
 try:dossier=review.prepare('Compare how fictional Lin sees themself with the system view.')
 finally:review.close()
 checks={
  'index_rebuild':rebuilt.get('chunks_added',0)>0,
  'reflect':bool(reflected.get('created') or reflected.get('action') in {'create','update'}),
  'ingest':applied.get('action')=='create',
  'context':pack['context_status'] in {'sufficient','partial'},
  'analyze':analysis['response_contract']['write_policy'].startswith('read_only'),
  'profile_review':dossier['review_mode']=='read_only',
  'validate':validated['valid'],
 }
 result={'passed':all(checks.values()),'checks':checks,'elapsed_ms':round((time.perf_counter()-started)*1000,2),'context_evidence':sum(len(pack[k]) for k in ('core_context','personal_evidence','external_knowledge','source_evidence'))}
 (ROOT/'work/demo-smoke-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
