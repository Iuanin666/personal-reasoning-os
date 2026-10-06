from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

DENIED_PARTS = {".git", ".venv", ".venv-ingest", "node_modules", "models", "work", ".setup-tmp", ".test-tmp", "__pycache__", ".personal-os"}
FORBIDDEN_PRIVATE_CONFIG_NAMES = {".private-patterns.json", "private-patterns.json", "private-denylist.json", "publisher-private-patterns.json", "local-private-patterns.json"}
GENERIC_PATTERNS = {
    "credential": re.compile(r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}"),
    "provider_token": re.compile(r"(?i)\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "phone_cn": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "source_id": re.compile(r"\bSRC-[A-F0-9]{16}\b", re.I),
    "absolute_windows_path": re.compile(r"\b[A-Z]:\\[^\r\n`\"'<>]+", re.I),
}
ALLOW_EMAIL = {"security@example.invalid", "maintainers@example.invalid"}
TEXT_EXT = {".md", ".py", ".ps1", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".txt", ".gitignore"}


def load_external_patterns(path: Path | None) -> list[re.Pattern[str]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = payload.get("patterns") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("private pattern file must contain a JSON list or a patterns list")
    patterns: list[re.Pattern[str]] = []
    for entry in entries:
        if isinstance(entry, str):
            patterns.append(re.compile(re.escape(entry), re.I))
        elif isinstance(entry, dict) and "literal" in entry:
            patterns.append(re.compile(re.escape(str(entry["literal"])), re.I))
        elif isinstance(entry, dict) and "regex" in entry:
            patterns.append(re.compile(str(entry["regex"]), re.I))
        else:
            raise ValueError("each private pattern requires a string, literal, or regex")
    return patterns


def _allowed(rule: str, value: str) -> bool:
    return rule == "email" and value.lower() in ALLOW_EMAIL


def scan(root: Path, private_pattern_file: Path | None = None) -> dict[str, object]:
    hits: list[dict[str, object]] = []
    files: list[str] = []
    external_patterns = load_external_patterns(private_pattern_file)
    paths: list[Path] = []
    for current, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if name not in DENIED_PARTS)
        paths.extend(Path(current) / name for name in sorted(filenames))
    for path in paths:
        relative = path.relative_to(root).as_posix()
        files.append(relative)
        if path.name.lower() in FORBIDDEN_PRIVATE_CONFIG_NAMES:
            hits.append({"rule": "forbidden_private_config", "file": relative, "line": 1})
            continue
        if path.suffix.lower() not in TEXT_EXT and path.name not in {".gitignore", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        if path.name == "PUBLIC_RELEASE_MANIFEST.json":
            text = re.sub(r'"[a-f0-9]{64}"', '"' + ("0" * 64) + '"', text, flags=re.I)
        for name, pattern in GENERIC_PATTERNS.items():
            for match in pattern.finditer(text):
                if not _allowed(name, match.group(0)):
                    hits.append({"rule": name, "file": relative, "line": text.count("\n", 0, match.start()) + 1})
        for pattern in external_patterns:
            for match in pattern.finditer(text):
                hits.append({"rule": "external_private_pattern", "file": relative, "line": text.count("\n", 0, match.start()) + 1})
    return {"root": ".", "files_scanned": len(files), "external_private_patterns_loaded": len(external_patterns), "unexplained_hits": hits, "passed": not hits}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--output")
    parser.add_argument("--private-patterns")
    args = parser.parse_args()
    configured = args.private_patterns or os.environ.get("PERSONAL_OS_PRIVATE_PATTERNS")
    private_patterns = Path(configured).resolve() if configured else None
    result = scan(Path(args.root).resolve(), private_patterns)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8", newline="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
