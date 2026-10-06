from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("privacy_scan", ROOT / "scripts" / "privacy_scan.py")
assert SPEC and SPEC.loader
privacy_scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(privacy_scan)


class PrivacyScannerContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_root = ROOT / ".test-tmp"
        cls.temp_root.mkdir(exist_ok=True)

    def test_external_patterns_detect_synthetic_private_path_without_echoing_it(self):
        with tempfile.TemporaryDirectory(dir=self.temp_root) as directory:
            root = Path(directory)
            synthetic = "X:" + "\\SyntheticPrivateVault\\records"
            (root / "note.md").write_text(f"local source: {synthetic}\n", encoding="utf-8")
            patterns = root.parent / f"{root.name}-external.json"
            patterns.write_text(json.dumps({"patterns": [{"literal": synthetic}]}), encoding="utf-8")
            try:
                result = privacy_scan.scan(root, patterns)
            finally:
                patterns.unlink(missing_ok=True)
            self.assertFalse(result["passed"])
            self.assertEqual(result["external_private_patterns_loaded"], 1)
            hit = next(item for item in result["unexplained_hits"] if item["rule"] == "external_private_pattern")
            self.assertNotIn("match", hit)
            self.assertNotIn(synthetic, json.dumps(result))

    def test_scanner_uses_external_configuration_for_publisher_specific_rules(self):
        source = (ROOT / "scripts" / "privacy_scan.py").read_text(encoding="utf-8")
        self.assertIn("load_external_patterns", source)
        self.assertIn("PERSONAL_OS_PRIVATE_PATTERNS", source)
        self.assertNotIn("private_drive", source)

    def test_public_tree_contains_no_private_denylist(self):
        present = [path for path in ROOT.rglob("*") if path.is_file() and path.name.lower() in privacy_scan.FORBIDDEN_PRIVATE_CONFIG_NAMES]
        self.assertEqual(present, [])

    def test_accidentally_copied_private_denylist_fails_gate(self):
        with tempfile.TemporaryDirectory(dir=self.temp_root) as directory:
            root = Path(directory)
            (root / ".private-patterns.json").write_text('{"patterns": []}\n', encoding="utf-8")
            result = privacy_scan.scan(root)
            self.assertFalse(result["passed"])
            self.assertEqual(result["unexplained_hits"][0]["rule"], "forbidden_private_config")


if __name__ == "__main__":
    unittest.main()
