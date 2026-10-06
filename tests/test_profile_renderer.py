from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import personal_os as pos, profile_evolution as pe

class ProfileHistoryRenderer(unittest.TestCase):
 def test_user_review_status_does_not_use_model_lifecycle_status(self):
  temp_root=ROOT/'.test-tmp';temp_root.mkdir(exist_ok=True)
  with tempfile.TemporaryDirectory(dir=temp_root) as raw:
   vault=Path(raw);(vault/'.obsidian').mkdir();config=Path(pos.initialize(vault,model=ROOT/'models/multilingual-minilm',register=False)['config']);root=vault/'PersonalOS'
   for n in (1,2):
    meta={'schema_version':1,'type':'experience','id':f'EXP-2030-000{n}','title':f'Synthetic event {n}','date':f'2030-0{n}-01','event_date':f'2030-0{n}-01','event_date_precision':'exact','recorded_at':'2030-03-01','created_at':'2030-03-01T10:00:00+00:00','updated_at':'2030-03-01T10:00:00+00:00','source':'synthetic regression fixture','provenance':'user_explicit'}
    p=root/'01_Experiences'/f"{meta['id']}.md";p.write_text(pos.dump(meta,f"# Synthetic event {n}\n\nFictional evidence."),encoding='utf-8')
   engine=pe.ProfileEvolution(config);dossier=engine.prepare('Synthetic review')
   proposal={'schema_version':'profile-evolution-proposal-v0.6','review_id':'REV-2030-public-test','review_date':'2030-03-02','self_view':[],'system_view':[{'id':'SY1','title':'Synthetic pattern','statement':'A bounded fictional pattern.','perspective':'system','evidence_basis':'inferred','evidence':['EXP-2030-0001','EXP-2030-0002'],'counter_evidence':[],'counter_search_summary':'Searched all synthetic records; no counterexample found.','scope':['synthetic testing'],'confidence':0.5,'status':'observing','user_review_status':'agree'}],'tensions':[],'evolution':[],'change_attribution':[],'profile_updates':[]}
   try:
    with patch.object(engine.store,'index',return_value={'updated':1}):engine.commit(proposal,dossier,{'SY1'},True)
   finally:engine.close()
   history=(root/'00_System/Profile_History.md').read_text(encoding='utf-8')
   self.assertIn('user_review_status: agree',history);self.assertNotIn('user_review_status: observing',history)

if __name__=='__main__':unittest.main()
