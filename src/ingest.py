"""Personal OS V0.3.1 Knowledge Ingest adapter.

Defuddle and Docling own extraction.  This module owns source identity,
provenance, deterministic planning, managed sources, CAS publication, and the
existing index hook.  Markdown remains authoritative.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml


INGEST_VERSION = "0.3.1"
KNOWLEDGE_TYPES = {"book", "article", "paper", "case", "framework"}
SOURCE_TYPES = {
    "original_book", "original_paper", "third_party_summary", "article",
    "case", "personal_reflection", "AI_summary",
}
CONTENT_ORIGINS = {
    "original_book": "original",
    "original_paper": "original",
    "article": "original",
    "case": "original",
    "third_party_summary": "third_party_summary",
    "AI_summary": "ai_summary",
    "personal_reflection": "personal_reflection",
}
TARGETS = {
    "book": "04_Knowledge/Books",
    "article": "04_Knowledge/Articles",
    "paper": "04_Knowledge/Papers",
    "case": "04_Knowledge/Cases",
    "framework": "04_Knowledge/Frameworks",
}
TRACKING_QUERY = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def file_hash(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.exists() else None


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def dump_note(meta: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n" + body.strip() + "\n"


def parse_note(text: str) -> tuple[dict, str]:
    match = re.match(r"\A\ufeff?---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not match:
        raise ValueError("Knowledge 笔记缺少 YAML frontmatter")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError("Knowledge YAML 必须是对象")
    return meta, text[match.end():].strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL 必须是 http/https")
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.casefold().startswith("utm_") or key.casefold() in TRACKING_QUERY:
            continue
        query.append((key, value))
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, urlencode(sorted(query)), ""))


def safe_name(value: str, fallback: str = "knowledge") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return (value[:100] or fallback)


def _version(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip().splitlines()[-1]


def extract_url(url: str, defuddle: Path) -> dict:
    canonical = canonical_url(url)
    command = [str(defuddle), "parse", canonical, "--json", "--markdown", "--lang", "zh-CN"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode:
        raise RuntimeError("Defuddle 提取失败: " + (result.stderr or result.stdout).strip()[-2000:])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Defuddle 未返回有效 JSON") from exc
    markdown = str(payload.get("content") or payload.get("markdown") or "").strip()
    if len(markdown) < 80:
        raise RuntimeError("Defuddle 提取内容过短，未发布")
    version = _version([str(defuddle), "--version"])
    snapshot = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    stable_payload = {key: value for key, value in payload.items() if key not in {"parseTime"}}
    stable_bytes = json.dumps(stable_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "source_format": "url",
        "canonical_url": canonical,
        "source_hash": sha256_bytes(stable_bytes),
        "title": payload.get("title") or canonical,
        "author": payload.get("author") or "",
        "published_at": payload.get("published") or payload.get("publishedTime") or None,
        "retrieved_at": now(),
        "extractor": "defuddle",
        "extractor_version": version,
        "markdown": markdown,
        "citations": [{"locator": heading, "text": ""} for heading in re.findall(r"^#{1,6}\s+(.+)$", markdown, re.M)[:100]],
        "managed_files": {"extracted.md": markdown.encode("utf-8"), "metadata.json": snapshot},
        "original_name": "extracted.md",
    }


def _docling_citations(document) -> list[dict]:
    citations: list[dict] = []
    seen = set()
    for item in getattr(document, "texts", []) or []:
        text = str(getattr(item, "text", "") or "").strip()
        for prov in getattr(item, "prov", []) or []:
            page = getattr(prov, "page_no", None)
            if page is None:
                continue
            key = (int(page), text)
            if key in seen:
                continue
            seen.add(key)
            citations.append({"locator": f"p.{int(page)}", "text": text})
            break
    return citations


def extract_document(path: Path, docling_python: Path) -> dict:
    if path.suffix.casefold() not in {".pdf", ".epub", ".docx"}:
        raise ValueError("MVP 仅支持 PDF、EPUB、DOCX")
    if not path.is_file():
        raise FileNotFoundError(path)
    script = r'''import importlib.metadata,json,sys
from pathlib import Path
from docling.document_converter import DocumentConverter
p=Path(sys.argv[1])
r=DocumentConverter().convert(p)
d=r.document
cit=[]
seen=set()
for item in (getattr(d,"texts",[]) or []):
    text=str(getattr(item,"text","") or "").strip()
    for prov in (getattr(item,"prov",[]) or []):
        page=getattr(prov,"page_no",None)
        if page is not None:
            key=(int(page),text)
            if key not in seen:
                seen.add(key);cit.append({"locator":f"p.{int(page)}","text":text})
            break
out={"version":importlib.metadata.version("docling"),"markdown":d.export_to_markdown(),"citations":cit,
     "name":getattr(d,"name",None)}
print(json.dumps(out,ensure_ascii=False))'''
    child_env = os.environ.copy()
    tool_root = docling_python.resolve().parents[2]
    child_env.setdefault("HF_HOME", str(tool_root / "models/docling-hf"))
    child_env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    child_env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run([str(docling_python), "-c", script, str(path.resolve())], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=900, env=child_env)
    if result.returncode:
        raise RuntimeError("Docling 提取失败: " + (result.stderr or result.stdout).strip()[-4000:])
    lines = [line for line in result.stdout.splitlines() if line.lstrip().startswith("{")]
    if not lines:
        raise RuntimeError("Docling 未返回提取结果")
    payload = json.loads(lines[-1])
    markdown = str(payload.get("markdown") or "").strip()
    if len(markdown) < 20:
        raise RuntimeError("Docling 提取内容过短，未发布")
    raw = path.read_bytes()
    ext = path.suffix.casefold().lstrip(".")
    citations = payload.get("citations") or []
    if not citations:
        citations = [{"locator": h, "text": ""} for h in re.findall(r"^#{1,6}\s+(.+)$", markdown, re.M)[:100]]
    return {
        "source_format": ext,
        "canonical_url": None,
        "source_hash": sha256_bytes(raw),
        "title": payload.get("name") or path.stem,
        "author": "",
        "published_at": None,
        "retrieved_at": now(),
        "extractor": "docling",
        "extractor_version": payload["version"],
        "markdown": markdown,
        "citations": citations,
        "managed_files": {path.name: raw, "extracted.md": markdown.encode("utf-8"),
                          "citation-index.json": (json.dumps(citations, ensure_ascii=False, indent=2) + "\n").encode("utf-8")},
        "original_name": path.name,
    }


def extract_text(text: str, name: str = "provided-text.txt") -> dict:
    text = text.strip()
    if not text:
        raise ValueError("文本不能为空")
    raw = text.encode("utf-8")
    original_name = safe_name(name, "provided-text.txt")
    managed = {original_name: raw}
    managed.setdefault("extracted.md", raw)
    return {
        "source_format": "plain_text",
        "canonical_url": None,
        "source_hash": sha256_bytes(raw),
        "title": safe_name(name.rsplit(".", 1)[0], "用户提供文本"),
        "author": "",
        "published_at": None,
        "retrieved_at": now(),
        "extractor": "direct-text",
        "extractor_version": INGEST_VERSION,
        "markdown": text,
        "citations": [],
        "managed_files": managed,
        "original_name": original_name,
    }


def load_root(config_path: Path) -> tuple[dict, Path]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    root = (config_path.parent / cfg["personal_os_root"]).resolve()
    return cfg, root


def knowledge_notes(root: Path):
    for folder in TARGETS.values():
        for path in sorted((root / folder).glob("*.md")):
            try:
                meta, body = parse_note(path.read_text(encoding="utf-8-sig"))
            except ValueError:
                continue
            if meta.get("type") == "knowledge":
                yield path, meta, body


def next_knowledge_id(root: Path, year: int) -> str:
    used = []
    for _, meta, _ in knowledge_notes(root):
        match = re.fullmatch(rf"KNOW-{year}-(\d{{4}})", str(meta.get("id", "")))
        if match:
            used.append(int(match.group(1)))
    return f"KNOW-{year}-{max(used, default=0) + 1:04d}"


def validate_packet(packet: dict) -> None:
    inp = packet.get("input") or {}
    if inp.get("kind") not in {"url", "file", "text"}:
        raise ValueError("input.kind 必须是 url/file/text")
    knowledge = packet.get("knowledge") or {}
    if knowledge.get("knowledge_type") not in KNOWLEDGE_TYPES:
        raise ValueError("knowledge_type 无效")
    if knowledge.get("source_type") not in SOURCE_TYPES:
        raise ValueError("source_type 无效")
    if inp["kind"] == "text" and knowledge["source_type"] not in {
        "third_party_summary", "personal_reflection", "AI_summary", "article", "case"
    }:
        raise ValueError("用户文本必须明确为总结、个人理解、文章或案例")
    if packet.get("source_id") and not re.fullmatch(r"SRC-[A-Z0-9_-]+", packet["source_id"]):
        raise ValueError("source_id 格式无效")


def perform_extraction(packet: dict, defuddle: Path, docling_python: Path) -> dict:
    inp = packet["input"]
    if inp["kind"] == "url":
        return extract_url(str(inp["value"]), defuddle)
    if inp["kind"] == "file":
        return extract_document(Path(inp["value"]).expanduser().resolve(), docling_python)
    return extract_text(str(inp["value"]), str(inp.get("name") or "provided-text.txt"))


def section_for(origin: str) -> str:
    return {
        "original": "可核验提取内容",
        "third_party_summary": "第三方总结",
        "ai_summary": "AI 摘要",
        "personal_reflection": "我的理解",
    }[origin]


def preserve_derived_sections(body: str) -> str:
    blocks = re.split(r"(?m)(?=^## )", body)
    keep = []
    for block in blocks:
        if re.match(r"^## (AI 摘要|第三方总结|我的理解)\s*$", block.splitlines()[0] if block else ""):
            keep.append(block.strip())
    return "\n\n".join(keep)


def document_outline(markdown: str, max_entries: int = 240, max_chars: int = 24000) -> str:
    """Build a deterministic navigation aid; this is not a summary."""
    toc = re.search(r"(?ms)^#{1,3}\s+目录\s*$\n(.*?)(?=^#{1,3}\s+|\Z)", markdown)
    if toc and toc.group(1).strip():
        rows = []
        for line in toc.group(1).splitlines():
            if not line.lstrip().startswith("|") or set(line.strip()) <= {"|", "-", ":"}:
                continue
            columns = line.strip().strip("|").split("|")
            title = re.split(r"(?:\s*\.\s*){3,}", columns[0].strip(), maxsplit=1)[0].strip()
            if not title:
                continue
            page_matches = re.findall(r"\d+", columns[-1]) if len(columns) > 1 else []
            row = f"- {title}" + (f"（p.{page_matches[-1]}）" if page_matches else "")
            if len("\n".join(rows + [row])) > max_chars:
                break
            rows.append(row)
            if len(rows) >= max_entries:
                break
        if rows:
            return "\n".join(rows)
    headings = []
    for match in re.finditer(r"^(#{1,4})\s+(.+?)\s*$", markdown, re.M):
        level, text = len(match.group(1)), match.group(2).strip()
        line = "  " * max(0, level - 1) + "- " + text
        if len("\n".join(headings + [line])) > max_chars:
            break
        headings.append(line)
        if len(headings) >= max_entries:
            break
    return "\n".join(headings) or "未识别到稳定的 Markdown 标题；请从 Source Evidence 查看完整提取内容。"


def make_body(title: str, origin: str, extraction: dict, managed_link: str,
              evidence_link: str | None = None,
              old_body: str | None = None, update_line: str | None = None) -> str:
    content = extraction["markdown"].strip()
    body = f"# {title}\n\n## 来源\n\n- Managed source: [{extraction['original_name']}]({managed_link})\n"
    if extraction.get("canonical_url"):
        body += f"- Canonical URL: {extraction['canonical_url']}\n"
    body += f"- SHA-256: `{extraction['source_hash']}`\n"
    body += f"- Extractor: {extraction['extractor']} {extraction['extractor_version']}\n\n"
    if origin == "original":
        body += "## 文档结构\n\n" + document_outline(content) + "\n\n"
        body += "## Source Evidence\n\n"
        if evidence_link:
            body += f"- 完整提取正文：[{extraction['extractor']} extraction]({evidence_link})\n"
        body += "- 完整正文与页码证据位于 managed source，并在 `source_evidence` 检索层中单独检索。\n"
        body += "- 本笔记未自动生成 AI 摘要或个人理解。\n"
    else:
        body += f"## {section_for(origin)}\n\n{content}\n"
    if old_body and origin == "original":
        derived = preserve_derived_sections(old_body)
        if derived:
            body += "\n" + derived + "\n"
    if update_line:
        body += f"\n## 来源更新历史\n\n- {update_line}\n"
    return body.strip() + "\n"


def make_plan(config_path: Path, packet: dict, defuddle: Path, docling_python: Path) -> dict:
    validate_packet(packet)
    _, root = load_root(config_path)
    extraction = perform_extraction(packet, defuddle, docling_python)
    knowledge = packet["knowledge"]
    origin = CONTENT_ORIGINS[knowledge["source_type"]]
    existing_notes = list(knowledge_notes(root))
    exact_source = next((m for _, m, _ in existing_notes if m.get("source_hash") == extraction["source_hash"]), None)
    same_url = next((m for _, m, _ in existing_notes
                     if extraction.get("canonical_url") and m.get("canonical_url") == extraction["canonical_url"]), None)
    source_id = packet.get("source_id") or (exact_source or same_url or {}).get("source_id")
    if not source_id:
        identity = extraction.get("canonical_url") or extraction["source_hash"]
        source_id = "SRC-" + sha256_text(extraction["source_format"] + ":" + identity)[:16].upper()
    candidates = [(p, m, b) for p, m, b in existing_notes
                  if m.get("source_id") == source_id and m.get("content_origin") == origin
                  and m.get("source_scope", "full") == knowledge.get("source_scope", "full")]
    existing = candidates[0] if candidates else None
    if len(candidates) > 1:
        raise ValueError("同一 source/origin/scope 对应多条记录，需要人工处理")
    resolution = packet.get("resolution")
    metadata_changed = False
    if existing:
        requested = {
            "title": knowledge.get("title"), "author": knowledge.get("author"),
            "quality": knowledge.get("quality"), "completeness": knowledge.get("completeness"),
            "verified_against_original": knowledge.get("verified_against_original"),
            "tags": knowledge.get("tags"), "citation_mode": knowledge.get("citation_mode"),
        }
        metadata_changed = any(value is not None and existing[1].get(key) != value
                               for key, value in requested.items())
    if existing and existing[1].get("source_type") != knowledge["source_type"]:
        action, reason = "conflict", "来源类型变化不能自动升级或改写"
    elif existing and existing[1].get("source_hash") == extraction["source_hash"] and metadata_changed and resolution == "update":
        action, reason = "update", "来源字节未变，已显式允许补充 Knowledge 元数据"
    elif existing and existing[1].get("source_hash") == extraction["source_hash"] and metadata_changed:
        action, reason = "conflict", "来源字节未变但 Knowledge 元数据不同，需要显式 resolution=update"
    elif existing and existing[1].get("source_hash") == extraction["source_hash"]:
        action, reason = "no-op", "相同 source_id、来源层和 SHA-256 已存在"
    elif existing and resolution == "update":
        action, reason = "update", "同一稳定 source_id 的内容变化，已显式允许更新"
    elif existing:
        action, reason = "conflict", "同一 source_id 的内容已变化，需要显式 resolution=update"
    else:
        action, reason = "create", "未找到相同 source_id、来源层和范围的 Knowledge Note"
    timestamp = now()
    import_id = packet.get("import_id") or "IMP-KNOW-" + sha256_text(source_id + extraction["source_hash"] + timestamp)[:16].upper()
    if existing:
        note_path, old_meta, old_body = existing
        note_id = old_meta["id"]
        expected_hash = file_hash(note_path)
        created_at = old_meta["created_at"]
        source_history = list(old_meta.get("source_history") or [])
        if action == "update" and old_meta.get("source_hash") != extraction["source_hash"]:
            source_history.append({"source_hash": old_meta.get("source_hash"),
                                   "source_path": old_meta.get("source_path"),
                                   "superseded_at": timestamp})
    else:
        year = datetime.fromisoformat(timestamp).year
        note_id = next_knowledge_id(root, year)
        title_seed = knowledge.get("title") or extraction.get("title") or note_id
        note_path = root / TARGETS[knowledge["knowledge_type"]] / f"{note_id} {safe_name(title_seed)}.md"
        old_meta, old_body, expected_hash, created_at, source_history = {}, None, None, timestamp, []
    version_rel = Path("04_Knowledge/_Sources") / source_id / "versions" / extraction["source_hash"][:12]
    original_rel = version_rel / extraction["original_name"]
    evidence_rel = version_rel / "extracted.md"
    note_rel = note_path.relative_to(root).as_posix()
    link_from_note = os.path.relpath(root / original_rel, note_path.parent).replace("\\", "/")
    evidence_link = os.path.relpath(root / evidence_rel, note_path.parent).replace("\\", "/")
    title = knowledge.get("title") or extraction.get("title") or note_id
    citation_mode = knowledge.get("citation_mode") or (
        "page" if any(str(x.get("locator", "")).startswith("p.") for x in extraction.get("citations", []))
        else ("section" if extraction.get("citations") else "none"))
    derived_status = dict(old_meta.get("derived_status") or {})
    source_bytes_changed = bool(existing and existing[1].get("source_hash") != extraction["source_hash"])
    if action == "update" and source_bytes_changed and old_body and "## AI 摘要" in old_body:
        derived_status["ai_summary"] = "needs_review"
    meta = dict(old_meta)
    meta.update({
        "schema_version": 1,
        "schema_revision": "knowledge-v0.3.1",
        "type": "knowledge",
        "id": note_id,
        "title": title,
        "knowledge_type": knowledge["knowledge_type"],
        "author": knowledge.get("author") or extraction.get("author") or None,
        "source_type": knowledge["source_type"],
        "content_origin": origin,
        "source_id": source_id,
        "source_format": extraction["source_format"],
        "source_path": original_rel.as_posix(),
        "source_evidence_path": evidence_rel.as_posix() if origin == "original" else None,
        "content_storage": "managed_source" if origin == "original" else "knowledge_note",
        "source_url": packet["input"].get("value") if packet["input"]["kind"] == "url" else None,
        "canonical_url": extraction.get("canonical_url"),
        "source_hash": extraction["source_hash"],
        "published_at": knowledge.get("published_at") or extraction.get("published_at"),
        "retrieved_at": extraction.get("retrieved_at"),
        "source_scope": knowledge.get("source_scope", "full"),
        "derived_from": list(knowledge.get("derived_from") or []),
        "citation_mode": citation_mode,
        "extractor": extraction["extractor"],
        "extractor_version": extraction["extractor_version"],
        "quality": knowledge.get("quality", "unassessed"),
        "completeness": knowledge.get("completeness", "full"),
        "verified_against_original": bool(knowledge.get("verified_against_original", origin == "original")),
        "date_added": old_meta.get("date_added") or timestamp[:10],
        "tags": list(knowledge.get("tags") or old_meta.get("tags") or []),
        "import_ids": list(dict.fromkeys(list(old_meta.get("import_ids") or []) + [import_id])),
        "source_history": source_history,
        "derived_status": derived_status,
        "created_at": created_at,
        "updated_at": timestamp,
    })
    update_line = None
    if action == "update":
        if source_bytes_changed:
            update_line = f"{timestamp}：`{old_meta.get('source_hash')}` → `{extraction['source_hash']}`；派生内容未被重写。"
        else:
            update_line = f"{timestamp}：来源字节未变，补充或修正 Knowledge 元数据。"
    body = make_body(title, origin, extraction, link_from_note, evidence_link, old_body, update_line)
    note_text = dump_note(meta, body)
    serial_files = {name: data.hex() for name, data in extraction["managed_files"].items()}
    plan = {
        "schema_version": "0.3",
        "created_at": timestamp,
        "config": str(config_path.resolve()),
        "import_id": import_id,
        "action": action,
        "reason": reason,
        "source_id": source_id,
        "source_hash": extraction["source_hash"],
        "note_id": note_id,
        "note_path": note_rel,
        "expected_note_hash": expected_hash,
        "source_version_path": version_rel.as_posix(),
        "managed_files_hex": serial_files,
        "source_manifest": {
            "source_id": source_id,
            "source_hash": extraction["source_hash"],
            "source_format": extraction["source_format"],
            "canonical_url": extraction.get("canonical_url"),
            "retrieved_at": extraction.get("retrieved_at"),
            "extractor": extraction["extractor"],
            "extractor_version": extraction["extractor_version"],
            "original_name": extraction["original_name"],
            "import_id": import_id,
        },
        "proposed_note": note_text,
    }
    cache = root / ".personal-os/cache/ingest"
    cache.mkdir(parents=True, exist_ok=True)
    plan_path = cache / f"{import_id}.json"
    atomic_text(plan_path, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    plan["plan_path"] = str(plan_path)
    return plan


@contextmanager
def write_lock(root: Path):
    lock_path = root / ".personal-os/write.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("另一个 Personal OS 写入正在运行") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _save_conflict(root: Path, plan: dict, reason: str) -> Path:
    folder = root / ".personal-os/conflicts"
    folder.mkdir(parents=True, exist_ok=True)
    operation_id = plan.get("import_id") or plan.get("migration_id") or "unknown-operation"
    path = folder / f"ingest-{safe_name(operation_id)}-{now().replace(':', '-')}.json"
    payload = {"type": "ingest_conflict", "reason": reason, "detected_at": now(),
               "plan": {k: v for k, v in plan.items() if k != "managed_files_hex"}}
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def apply_plan(plan_path: Path, index_python: Path | None = None, index_cli: Path | None = None,
               fail_after_source: bool = False) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    config_path = Path(plan["config"])
    _, root = load_root(config_path)
    if plan["action"] == "no-op":
        return {"action": "no-op", "note_id": plan["note_id"], "source_id": plan["source_id"], "index": "unchanged"}
    if plan["action"] == "conflict":
        artifact = _save_conflict(root, plan, plan["reason"])
        return {"action": "conflict", "reason": plan["reason"], "artifact": str(artifact)}
    note_path = (root / plan["note_path"]).resolve()
    source_version = (root / plan["source_version_path"]).resolve()
    if not note_path.is_relative_to(root) or not source_version.is_relative_to(root / "04_Knowledge/_Sources"):
        raise ValueError("发布路径越界")
    current_hash = file_hash(note_path)
    if current_hash != plan.get("expected_note_hash"):
        artifact = _save_conflict(root, plan, "Knowledge Note 在规划后发生变化")
        return {"action": "conflict", "reason": "CAS hash mismatch", "artifact": str(artifact)}
    stage_parent = root / ".personal-os/cache/ingest-staging"
    stage_parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=safe_name(plan["import_id"]) + "-", dir=stage_parent))
    staged_source = stage / "source-version"
    staged_source.mkdir()
    for name, value in plan["managed_files_hex"].items():
        target = staged_source / safe_name(name)
        target.write_bytes(bytes.fromhex(value))
    (staged_source / "source-manifest.yaml").write_text(
        yaml.safe_dump(plan["source_manifest"], allow_unicode=True, sort_keys=False), encoding="utf-8")
    source_created = False
    try:
        with write_lock(root):
            if file_hash(note_path) != plan.get("expected_note_hash"):
                artifact = _save_conflict(root, plan, "Knowledge Note 在提交前发生变化")
                return {"action": "conflict", "reason": "CAS hash mismatch", "artifact": str(artifact)}
            if source_version.exists():
                manifest = source_version / "source-manifest.yaml"
                existing = yaml.safe_load(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
                if existing.get("source_hash") != plan["source_hash"]:
                    artifact = _save_conflict(root, plan, "managed source version 路径已存在但 hash 不同")
                    return {"action": "conflict", "reason": "managed source collision", "artifact": str(artifact)}
            else:
                source_version.parent.mkdir(parents=True, exist_ok=True)
                staged_source.replace(source_version)
                source_created = True
            if fail_after_source:
                raise RuntimeError("injected failure after managed source")
            atomic_text(note_path, plan["proposed_note"])
    except BaseException:
        if source_created and source_version.exists():
            shutil.rmtree(source_version)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    index_result: dict | str = "skipped"
    if index_python and index_cli:
        result = subprocess.run([str(index_python), str(index_cli), "--config", str(config_path), "index"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if result.returncode:
            index_result = {"status": "failed", "error": (result.stderr or result.stdout).strip()[-2000:]}
        else:
            index_result = json.loads(result.stdout)
    return {"action": plan["action"], "note_id": plan["note_id"], "source_id": plan["source_id"],
            "note_path": str(note_path), "managed_source": str(source_version), "index": index_result}


def make_boundary_migration_plan(config_path: Path, note_id: str, docling_python: Path,
                                 refresh_citations: bool = False) -> dict:
    """Plan V0.3 -> V0.3.1 compaction without changing IDs or source evidence."""
    _, root = load_root(config_path)
    matches = [(p, m, b) for p, m, b in knowledge_notes(root) if m.get("id") == note_id]
    if len(matches) != 1:
        raise ValueError(f"未找到唯一 Knowledge Note: {note_id}")
    note_path, meta, old_body = matches[0]
    if meta.get("content_origin") != "original":
        raise ValueError("边界迁移只适用于 original Knowledge Note")
    source = (root / meta["source_path"]).resolve()
    if not source.is_file() or not source.is_relative_to(root / "04_Knowledge/_Sources"):
        raise ValueError("managed source 不存在或路径越界")
    if sha256_bytes(source.read_bytes()) != meta.get("source_hash"):
        raise ValueError("原始来源 SHA-256 与 Knowledge metadata 不一致")
    extracted = source.parent / "extracted.md"
    if not extracted.is_file():
        raise ValueError("managed source 缺少 extracted.md")
    markdown = extracted.read_text(encoding="utf-8-sig")
    citation_path = source.parent / "citation-index.json"
    old_citations = citation_path.read_bytes() if citation_path.exists() else b"[]\n"
    proposed_citations = None
    if refresh_citations:
        refreshed = extract_document(source, docling_python)
        if refreshed["source_hash"] != meta["source_hash"]:
            raise ValueError("重新提取时原始来源 hash 发生变化")
        proposed_citations = (json.dumps(refreshed.get("citations") or [], ensure_ascii=False, indent=2) + "\n")
    evidence_rel = extracted.relative_to(root).as_posix()
    original_rel = source.relative_to(root).as_posix()
    original_link = os.path.relpath(source, note_path.parent).replace("\\", "/")
    evidence_link = os.path.relpath(extracted, note_path.parent).replace("\\", "/")
    extraction = {
        "original_name": source.name, "source_hash": meta["source_hash"],
        "extractor": meta.get("extractor", "docling"),
        "extractor_version": meta.get("extractor_version", "unknown"),
        "markdown": markdown, "canonical_url": meta.get("canonical_url"), "citations": [],
    }
    new_meta = dict(meta)
    new_meta.update({
        "schema_revision": "knowledge-v0.3.1",
        "source_path": original_rel,
        "source_evidence_path": evidence_rel,
        "content_storage": "managed_source",
        "updated_at": now(),
    })
    new_body = make_body(meta["title"], "original", extraction, original_link, evidence_link, old_body)
    proposed_note = dump_note(new_meta, new_body)
    action = "no-op" if proposed_note == note_path.read_text(encoding="utf-8-sig") and proposed_citations is None else "migrate"
    migration_id = "MIG-KNOW-031-" + note_id
    plan = {
        "schema_version": "0.3.1", "migration_id": migration_id, "created_at": now(),
        "config": str(config_path.resolve()), "action": action, "note_id": note_id,
        "source_id": meta["source_id"], "source_hash": meta["source_hash"],
        "note_path": note_path.relative_to(root).as_posix(),
        "expected_note_hash": file_hash(note_path), "proposed_note": proposed_note,
        "source_path": original_rel, "source_evidence_path": evidence_rel,
        "expected_extracted_hash": file_hash(extracted),
        "citation_path": citation_path.relative_to(root).as_posix(),
        "expected_citation_hash": sha256_bytes(old_citations),
        "proposed_citations": proposed_citations,
    }
    cache = root / ".personal-os/cache/ingest"
    cache.mkdir(parents=True, exist_ok=True)
    plan_path = cache / f"{migration_id}.json"
    atomic_text(plan_path, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    plan["plan_path"] = str(plan_path)
    return plan


def apply_boundary_migration(plan_path: Path, index_python: Path | None = None,
                             index_cli: Path | None = None, fail_after_note: bool = False) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    config_path = Path(plan["config"])
    _, root = load_root(config_path)
    if plan["action"] == "no-op":
        return {"action": "no-op", "note_id": plan["note_id"], "source_id": plan["source_id"]}
    note_path = (root / plan["note_path"]).resolve()
    source_path = (root / plan["source_path"]).resolve()
    evidence_path = (root / plan["source_evidence_path"]).resolve()
    citation_path = (root / plan["citation_path"]).resolve()
    if not note_path.is_relative_to(root) or not evidence_path.is_relative_to(root / "04_Knowledge/_Sources"):
        raise ValueError("迁移路径越界")
    if file_hash(note_path) != plan["expected_note_hash"]:
        artifact = _save_conflict(root, plan, "Knowledge Note 在迁移规划后发生变化")
        return {"action": "conflict", "reason": "CAS hash mismatch", "artifact": str(artifact)}
    if file_hash(source_path) != plan["source_hash"] or file_hash(evidence_path) != plan["expected_extracted_hash"]:
        artifact = _save_conflict(root, plan, "managed source 在迁移规划后发生变化")
        return {"action": "conflict", "reason": "source CAS hash mismatch", "artifact": str(artifact)}
    current_citation_hash = file_hash(citation_path) or sha256_bytes(b"[]\n")
    if current_citation_hash != plan["expected_citation_hash"]:
        artifact = _save_conflict(root, plan, "citation index 在迁移规划后发生变化")
        return {"action": "conflict", "reason": "citation CAS hash mismatch", "artifact": str(artifact)}
    backup_dir = root / ".personal-os/migrations/v0.3.1" / plan["migration_id"]
    if backup_dir.exists():
        raise RuntimeError("迁移备份已存在；请先检查或回滚: " + str(backup_dir))
    backup_dir.mkdir(parents=True)
    old_note_bytes = note_path.read_bytes()
    old_config_bytes = config_path.read_bytes()
    old_citation_bytes = citation_path.read_bytes() if citation_path.exists() else b"[]\n"
    old_note = old_note_bytes.decode("utf-8-sig")
    old_config = old_config_bytes.decode("utf-8-sig")
    atomic_bytes(backup_dir / "knowledge-note.before.md", old_note_bytes)
    atomic_bytes(backup_dir / "citation-index.before.json", old_citation_bytes)
    atomic_bytes(backup_dir / "config.before.yaml", old_config_bytes)
    config_expected = file_hash(config_path)
    cfg = yaml.safe_load(old_config) or {}
    cfg["personal_os_version"] = "0.3.1"
    cfg["knowledge_ingest_version"] = "0.3.1"
    cfg.setdefault("search", {})["source_evidence_default"] = "intent_only"
    try:
        with write_lock(root):
            if file_hash(note_path) != plan["expected_note_hash"] or file_hash(config_path) != config_expected:
                raise RuntimeError("CAS conflict during boundary migration")
            if plan.get("proposed_citations") is not None:
                atomic_text(citation_path, plan["proposed_citations"])
            atomic_text(note_path, plan["proposed_note"])
            if fail_after_note:
                raise RuntimeError("injected failure after compact note")
            atomic_text(config_path, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    except BaseException:
        atomic_bytes(note_path, old_note_bytes)
        atomic_bytes(citation_path, old_citation_bytes)
        atomic_bytes(config_path, old_config_bytes)
        raise
    manifest = {
        "migration_id": plan["migration_id"], "applied_at": now(),
        "config": str(config_path.resolve()),
        "note_id": plan["note_id"], "source_id": plan["source_id"],
        "source_hash": plan["source_hash"], "note_path": plan["note_path"],
        "before_note_hash": plan["expected_note_hash"], "after_note_hash": file_hash(note_path),
        "source_path": plan["source_path"], "source_evidence_path": plan["source_evidence_path"],
        "source_evidence_hash": file_hash(evidence_path),
        "citation_path": plan["citation_path"], "after_citation_hash": file_hash(citation_path),
        "after_config_hash": file_hash(config_path),
        "backup_dir": str(backup_dir),
    }
    atomic_text(backup_dir / "migration-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    index_result: dict | str = "skipped"
    if index_python and index_cli:
        result = subprocess.run([str(index_python), str(index_cli), "--config", str(config_path), "rebuild"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        index_result = json.loads(result.stdout) if result.returncode == 0 else {
            "status": "failed", "error": (result.stderr or result.stdout).strip()[-2000:]}
    return {"action": "migrate", "note_id": plan["note_id"], "source_id": plan["source_id"],
            "note_path": str(note_path), "manifest": str(backup_dir / "migration-manifest.json"),
            "index": index_result}


def rollback_boundary_migration(manifest_path: Path, index_python: Path | None = None,
                                index_cli: Path | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    backup = manifest_path.parent
    config_path = Path(manifest["config"])
    _, root = load_root(config_path)
    note_path = root / manifest["note_path"]
    source_path = root / manifest["source_path"]
    evidence_path = root / manifest["source_evidence_path"]
    citation_path = root / manifest.get("citation_path", str(Path(manifest["source_path"]).parent / "citation-index.json"))
    changed = []
    checks = [
        (note_path, manifest["after_note_hash"], "Knowledge Note"),
        (config_path, manifest.get("after_config_hash"), "config"),
        (citation_path, manifest.get("after_citation_hash"), "citation index"),
        (source_path, manifest["source_hash"], "managed source"),
        (evidence_path, manifest.get("source_evidence_hash"), "extracted source evidence"),
    ]
    for path, expected, label in checks:
        if expected and file_hash(path) != expected:
            changed.append(label)
    if changed:
        artifact = _save_conflict(root, manifest, "迁移后文件已修改；拒绝回滚覆盖: " + ", ".join(changed))
        return {"action": "conflict", "reason": "rollback CAS hash mismatch", "artifact": str(artifact)}
    with write_lock(root):
        atomic_bytes(note_path, (backup / "knowledge-note.before.md").read_bytes())
        atomic_bytes(citation_path, (backup / "citation-index.before.json").read_bytes())
        atomic_bytes(config_path, (backup / "config.before.yaml").read_bytes())
    index_result: dict | str = "skipped"
    if index_python and index_cli:
        result = subprocess.run([str(index_python), str(index_cli), "--config", str(config_path), "rebuild"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        index_result = json.loads(result.stdout) if result.returncode == 0 else {
            "status": "failed", "error": (result.stderr or result.stdout).strip()[-2000:]}
    return {"action": "rollback", "note_id": manifest["note_id"], "source_id": manifest["source_id"],
            "index": index_result}


def tool_versions(defuddle: Path, docling_python: Path) -> dict:
    script = "import importlib.metadata as m; print(m.version('docling'))"
    result = subprocess.run([str(docling_python), "-c", script], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120)
    return {"ingest": INGEST_VERSION, "defuddle": _version([str(defuddle), "--version"]),
            "docling": result.stdout.strip() if result.returncode == 0 else "unavailable",
            "docling_error": None if result.returncode == 0 else result.stderr.strip()[-1000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Personal OS Knowledge Ingest adapter")
    parser.add_argument("--config", required=True)
    parser.add_argument("--defuddle", required=True)
    parser.add_argument("--docling-python", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    p = sub.add_parser("plan"); p.add_argument("--input", required=True)
    p = sub.add_parser("apply"); p.add_argument("--plan", required=True); p.add_argument("--index-python"); p.add_argument("--index-cli")
    p = sub.add_parser("plan-boundary"); p.add_argument("--note-id", required=True); p.add_argument("--refresh-citations", action="store_true")
    p = sub.add_parser("apply-boundary"); p.add_argument("--plan", required=True); p.add_argument("--index-python"); p.add_argument("--index-cli")
    p = sub.add_parser("rollback-boundary"); p.add_argument("--manifest", required=True); p.add_argument("--index-python"); p.add_argument("--index-cli")
    args = parser.parse_args()
    config, defuddle, docling_python = Path(args.config), Path(args.defuddle), Path(args.docling_python)
    if args.command == "version":
        output = tool_versions(defuddle, docling_python)
    elif args.command == "plan":
        packet = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        plan = make_plan(config, packet, defuddle, docling_python)
        output = {k: v for k, v in plan.items() if k not in {"managed_files_hex", "proposed_note"}}
    elif args.command == "apply":
        output = apply_plan(Path(args.plan), Path(args.index_python) if args.index_python else None,
                            Path(args.index_cli) if args.index_cli else None)
    elif args.command == "plan-boundary":
        plan = make_boundary_migration_plan(config, args.note_id, docling_python, args.refresh_citations)
        output = {k: v for k, v in plan.items() if k not in {"proposed_note", "proposed_citations"}}
    elif args.command == "apply-boundary":
        output = apply_boundary_migration(Path(args.plan), Path(args.index_python) if args.index_python else None,
                                          Path(args.index_cli) if args.index_cli else None)
    else:
        output = rollback_boundary_migration(Path(args.manifest), Path(args.index_python) if args.index_python else None,
                                             Path(args.index_cli) if args.index_cli else None)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
