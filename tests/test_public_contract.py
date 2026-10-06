from __future__ import annotations
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import personal_os as pos,context_engine,analyze,profile_evolution

class PublicContract(unittest.TestCase):
 def test_versions(self):
  self.assertEqual(pos.PERSONAL_OS_VERSION,'0.6.1');self.assertEqual(context_engine.CONTEXT_VERSION,'0.4.1');self.assertEqual(analyze.ANALYZE_VERSION,'0.5.1');self.assertEqual(profile_evolution.PROFILE_EVOLUTION_VERSION,'0.6.1')
 def test_demo_is_marked_synthetic(self):self.assertIn('fictional',(ROOT/'examples/demo-vault/SYNTHETIC_DATA.md').read_text(encoding='utf-8').lower())
 def test_no_runtime_is_bundled_in_skills(self):
  self.assertFalse(any(p.name in {'runtime.json','installed-release.json'} for p in (ROOT/'skills').rglob('*')))

if __name__=='__main__':unittest.main()
