"""Personal OS 0.6 Profile Evolution review and confirmed commit.

Review is read-only.  Codex synthesizes a proposal from the bounded dossier;
this module validates provenance/evidence rules and performs an explicit CAS
commit.  Markdown remains authoritative.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
import time
from typing import Any

import personal_os as pos

PROFILE_EVOLUTION_VERSION = "0.6.1"
PROPOSAL_SCHEMA = "profile-evolution-proposal-v0.6"
CAUSAL_LEVELS = {"explicit_cause", "supported_hypothesis", "possible_influence", "unknown"}
CHANGE_TYPES = {"new", "strengthened", "weakened", "reframed", "stable", "contradicted", "retired"}
REVIEW_STATUSES = {"unreviewed", "agree", "partially_agree", "disagree"}
SELF_SOURCES = {"user_explicit", "self_authored", "personal_reflection"}
EVIDENCE_TYPES = {"experience", "decision", "project", "model", "profile", "principle", "history", "knowledge"}


def _profile_items(body: str) -> list[dict]:
    items = []
    pattern = re.compile(r"<!-- item:([^ ]+) -->\n(.*?)\n<!-- /item -->", re.S)
    for match in pattern.finditer(body):
        block = match.group(2)
        statement = next((x[2:] for x in block.splitlines() if x.startswith("- ")), "")
        evidence = re.findall(r"\[\[([^]|#]+)", block)
        items.append({"id": match.group(1), "statement": statement, "evidence": evidence,
                      "perspective": "self", "evidence_basis": "explicit"})
    return items


def _effective(meta: dict) -> str | None:
    for key in ("event_date", "date", "outcome_date", "created_at"):
        value = meta.get(key)
        if value:
            return str(value)[:10]
    raw = str(meta.get("event_date_raw") or "")
    match = re.search(r"20\d{2}", raw)
    return match.group(0) if match else None


class ProfileEvolution:
    def __init__(self, config: Path, read_only: bool = True):
        self.config = Path(config).resolve()
        self.store = pos.Store(self.config, read_only=read_only)
        self.root = self.store.root

    def close(self):
        for handler in list(self.store.log.handlers):
            handler.close(); self.store.log.removeHandler(handler)

    def prepare(self, question: str, as_of: str | None = None, max_notes: int = 60,
                max_chars: int = 60000) -> dict:
        started = time.perf_counter()
        if as_of and not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", as_of):
            raise ValueError("as_of 必须是 YYYY、YYYY-MM 或 YYYY-MM-DD")
        notes, snapshots, self_view, system_view, checkpoints = [], {}, [], [], []
        candidates = []
        allowed = EVIDENCE_TYPES
        for path in self.store.notes():
            raw = path.read_text(encoding="utf-8-sig")
            meta, body = pos.parse(raw)
            rel = path.relative_to(self.root).as_posix()
            snapshots[rel] = pos.file_digest(path)
            if meta.get("type") == "profile": self_view.extend(_profile_items(body))
            if meta.get("type") == "model":
                system_view.append({"id": meta["id"], "statement": meta.get("title"),
                    "perspective": meta.get("perspective", "system"),
                    "evidence_basis": meta.get("evidence_basis", "inferred"),
                    "confidence": meta.get("confidence"), "status": meta.get("status"),
                    "user_review_status": meta.get("user_review_status", "unreviewed"),
                    "evidence": meta.get("evidence", []), "counter_evidence": meta.get("counter_evidence", [])})
            if meta.get("type") == "history":
                checkpoints = re.findall(r"^## (REV-[^\n]+)", body, re.M)
            if meta.get("type") not in allowed: continue
            if meta.get("type") == "knowledge" and not (meta.get("content_origin") == "personal_reflection" or meta.get("source_type") == "personal_reflection"):
                continue
            effective = _effective(meta)
            if as_of and effective and effective > as_of: continue
            candidates.append((effective or "0000", rel, meta, body))
        candidates.sort(key=lambda x: (x[0], x[1]))
        used = 0
        for effective, rel, meta, body in candidates[-max_notes:]:
            excerpt = re.sub(r"\n{3,}", "\n\n", body).strip()[:2800]
            if used + len(excerpt) > max_chars: break
            used += len(excerpt)
            notes.append({"note_id": meta["id"], "note_type": meta["type"], "title": meta.get("title"),
                          "path": rel, "effective_date": effective if effective != "0000" else None,
                          "event_date_precision": meta.get("event_date_precision"),
                          "provenance": meta.get("provenance", "system_record"),
                          "domains": meta.get("domains", []), "related_experiences": meta.get("related_experiences", []),
                          "related_decisions": meta.get("related_decisions", []), "excerpt": excerpt})
        counts = Counter(x["note_type"] for x in notes)
        return {"schema_version": "profile-evolution-dossier-v0.6", "review_mode": "read_only",
                "question": question, "as_of": as_of, "prepared_at": pos.now(),
                "current_self_view": self_view, "current_system_view": system_view,
                "review_checkpoints": checkpoints, "evidence_pool": notes,
                "base_snapshots": snapshots,
                "rules": {"self_view_requires_explicit_expression": True,
                          "system_view_min_distinct_evidence": 2,
                          "counter_evidence_search_required": True,
                          "single_event_confidence_cap": 0.39,
                          "causal_levels": sorted(CAUSAL_LEVELS),
                          "no_source_evidence_scan": True, "no_automatic_commit": True},
                "metrics": {"note_count": len(notes), "note_types": dict(counts), "used_chars": used,
                            "retrieval_ms": round((time.perf_counter()-started)*1000, 2)}}

    @staticmethod
    def validate_proposal(proposal: dict, dossier: dict) -> dict:
        failures, warnings = [], []
        if proposal.get("schema_version") != PROPOSAL_SCHEMA: failures.append("schema_version")
        if not proposal.get("review_id") or not re.fullmatch(r"REV-[A-Za-z0-9_-]+", proposal.get("review_id", "")):
            failures.append("review_id")
        known = {x["note_id"]: x for x in dossier.get("evidence_pool", [])}
        self_ids, system_ids = set(), set()
        for item in proposal.get("self_view", []):
            self_ids.add(item.get("id"))
            if item.get("source_kind") not in SELF_SOURCES: failures.append(f"{item.get('id')}:self_source")
            if not item.get("evidence"): failures.append(f"{item.get('id')}:self_evidence")
            for ref in item.get("evidence", []):
                if ref not in known: failures.append(f"{item.get('id')}:unknown_evidence:{ref}")
                elif item["source_kind"] == "user_explicit" and known[ref].get("provenance") != "user_explicit":
                    failures.append(f"{item.get('id')}:not_explicit:{ref}")
        for item in proposal.get("system_view", []):
            iid = item.get("id"); system_ids.add(iid)
            evidence = list(dict.fromkeys(item.get("evidence", [])))
            counter = list(dict.fromkeys(item.get("counter_evidence", [])))
            if len(evidence) < 2: failures.append(f"{iid}:system_needs_multiple_evidence")
            if "counter_evidence" not in item or not item.get("counter_search_summary"):
                failures.append(f"{iid}:counter_search_missing")
            if item.get("perspective") != "system" or item.get("evidence_basis") != "inferred":
                failures.append(f"{iid}:system_identity")
            if item.get("user_review_status", "unreviewed") not in REVIEW_STATUSES:
                failures.append(f"{iid}:review_status")
            for ref in evidence + counter:
                if ref not in known: failures.append(f"{iid}:unknown_evidence:{ref}")
            confidence = float(item.get("confidence", 0))
            domains = {d for ref in evidence for d in known.get(ref, {}).get("domains", [])}
            dates = {str(known.get(ref, {}).get("effective_date") or "")[:4] for ref in evidence if known.get(ref)}
            if len(evidence) == 1 and confidence > .39: failures.append(f"{iid}:single_event_overconfidence")
            if confidence >= .8 and (len(evidence) < 3 or len(domains) < 2):
                failures.append(f"{iid}:high_confidence_without_cross_context")
            if len(domains) < 2: warnings.append(f"{iid}:scope_should_be_narrow")
            if len(dates - {""}) < 2: warnings.append(f"{iid}:cross_time_not_established")
        for item in proposal.get("tensions", []):
            if item.get("self_view_id") not in self_ids or item.get("system_view_id") not in system_ids:
                failures.append(f"{item.get('id')}:tension_reference")
            if item.get("status") not in REVIEW_STATUSES: failures.append(f"{item.get('id')}:tension_status")
        for item in proposal.get("alignments", []):
            if item.get("self_view_id") not in self_ids or item.get("system_view_id") not in system_ids:
                failures.append(f"{item.get('id')}:alignment_reference")
        for item in proposal.get("evolution", []):
            if item.get("change_type") not in CHANGE_TYPES: failures.append(f"{item.get('id')}:change_type")
        for item in proposal.get("change_attribution", []):
            level = item.get("level")
            if level not in CAUSAL_LEVELS: failures.append(f"{item.get('id')}:causal_level")
            if level == "explicit_cause" and (not item.get("evidence") or not item.get("explicit_statement")):
                failures.append(f"{item.get('id')}:explicit_cause_needs_user_statement")
            if level == "unknown" and item.get("explanation") not in (None, "", "unknown", "无法可靠解释"):
                failures.append(f"{item.get('id')}:unknown_must_not_claim_cause")
        for change in proposal.get("profile_updates", []):
            if change.get("self_view_id") not in self_ids: failures.append(f"profile_update:{change.get('key')}:not_self_view")
            if change.get("action") not in {"add", "update", "keep", "retire"}: failures.append("profile_update_action")
        return {"valid": not failures, "failures": sorted(set(failures)), "warnings": sorted(set(warnings)),
                "counts": {"self_view": len(self_ids), "system_view": len(system_ids),
                           "tensions": len(proposal.get("tensions", [])), "changes": len(proposal.get("evolution", []))}}

    def commit(self, proposal: dict, dossier: dict, accepted_ids: set[str], confirmed: bool = False) -> dict:
        if not confirmed: raise ValueError("Profile Review 默认只读；commit 必须显式确认")
        validation = self.validate_proposal(proposal, dossier)
        if not validation["valid"]: raise ValueError("proposal 校验失败: " + ", ".join(validation["failures"]))
        review_id = proposal["review_id"]
        history_path = self.root / "00_System" / "Profile_History.md"
        profile_path = self.root / "00_System" / "Profile.md"
        base = dossier.get("base_snapshots", {})
        staged: dict[Path, str] = {}; expected: dict[Path, str | None] = {}
        with self.store.lock():
            for target in (history_path, profile_path):
                rel = target.relative_to(self.root).as_posix()
                if rel not in base: raise ValueError("dossier 缺少基础 hash: " + rel)
            hmeta, hbody = pos.parse(history_path.read_text(encoding="utf-8-sig"))
            if re.search(r"^## " + re.escape(review_id) + r"\b", hbody, re.M):
                return {"duplicate": True, "review_id": review_id}
            selected_system = [x for x in proposal.get("system_view", []) if x.get("id") in accepted_ids]
            selected_tensions = [x for x in proposal.get("tensions", []) if x.get("id") in accepted_ids]
            selected_evolution = [x for x in proposal.get("evolution", []) if x.get("id") in accepted_ids]
            selected_causes = [x for x in proposal.get("change_attribution", []) if x.get("id") in accepted_ids]
            section = [f"## {review_id} — Profile Review Checkpoint", "", f"review_date: {proposal.get('review_date') or date.today().isoformat()}", ""]
            for title, rows in (("Self View", [x for x in proposal.get("self_view", []) if x.get("id") in accepted_ids]),
                                ("System View", selected_system), ("View Differences", selected_tensions),
                                ("Evolution", selected_evolution), ("Change Attribution", selected_causes)):
                section += [f"### {title}", ""]
                if not rows: section += ["- 本次未确认条目。", ""]; continue
                for item in rows:
                    statement = item.get("statement") or item.get("explanation") or item.get("to") or item.get("interpretation") or ""
                    links = sorted(set(item.get("evidence", [])))
                    section.append(f"- **{item.get('id')}** {statement}")
                    section.append("  - evidence: " + (", ".join(f"[[{x}]]" for x in links) if links else "无"))
                    if item.get("level"): section.append("  - attribution_level: " + item["level"])
                    if item.get("user_review_status"):
                        section.append("  - user_review_status: " + item["user_review_status"])
                    if item.get("counter_evidence") is not None:
                        section.append("  - counter_evidence: " + (", ".join(f"[[{x}]]" for x in item["counter_evidence"]) or "未发现；已执行反例搜索"))
                section.append("")
            hmeta = dict(hmeta); hmeta["updated_at"] = pos.now(); hmeta["schema_revision"] = "profile-evolution-v0.6"
            hmeta["profile_review_checkpoints"] = list(dict.fromkeys(hmeta.get("profile_review_checkpoints", []) + [review_id]))
            staged[history_path] = pos.dump(hmeta, hbody + "\n\n" + "\n".join(section))
            expected[history_path] = base[history_path.relative_to(self.root).as_posix()]

            pmeta, pbody = pos.parse(profile_path.read_text(encoding="utf-8-sig"))
            for upd in proposal.get("profile_updates", []):
                if upd.get("id") not in accepted_ids or upd.get("self_view_id") not in accepted_ids or upd.get("action") == "keep": continue
                key = upd["key"]
                pattern = re.compile(r"<!-- item:" + re.escape(key) + r" -->\n(.*?)\n<!-- /item -->", re.S)
                found = pattern.search(pbody)
                if upd["action"] == "retire":
                    if found: pbody = pattern.sub("", pbody)
                    continue
                if upd["action"] == "update" and not found: raise ValueError("Profile update key 不存在: " + key)
                block = (f"<!-- item:{key} -->\n- {upd['value']}\n  - perspective: self\n  - evidence_basis: explicit\n"
                         f"  - provenance: user_explicit\n  - evidence: " + ", ".join(f"[[{x}]]" for x in upd.get("evidence", [])) +
                         f"\n  - last_confirmed: {proposal.get('review_date') or date.today().isoformat()}\n<!-- /item -->")
                pbody = pattern.sub(block, pbody) if found else pbody.rstrip() + "\n\n" + block
            pmeta = dict(pmeta); pmeta["updated_at"] = pos.now(); pmeta["schema_revision"] = "profile-evolution-v0.6"
            staged[profile_path] = pos.dump(pmeta, pbody)
            expected[profile_path] = base[profile_path.relative_to(self.root).as_posix()]

            existing_ids = {pos.parse(p.read_text(encoding="utf-8-sig"))[0]["id"] for p in self.store.notes()}
            next_no = max([int(x.split("-")[-1]) for x in existing_ids if re.fullmatch(r"MOD-\d{4}-\d{4}", x)] or [0])
            for item in selected_system:
                model_id = item.get("model_id")
                if model_id:
                    path = self.root / "05_Models" / f"{model_id}.md"
                    if not path.exists(): raise ValueError("指定 Model 不存在: " + model_id)
                    meta, body = pos.parse(path.read_text(encoding="utf-8-sig"))
                    rel = path.relative_to(self.root).as_posix()
                    if rel not in base: raise ValueError("dossier 缺少 Model hash: " + rel)
                    expected[path] = base[rel]
                    body += f"\n\n## Profile Review / {review_id}\n\n{item['statement']}"
                else:
                    next_no += 1; model_id = f"MOD-{date.today().year}-{next_no:04d}"
                    path = self.root / "05_Models" / f"{model_id}.md"; body = "# " + item.get("title", item["statement"][:40])
                    meta = {"schema_version": 1, "schema_revision": "profile-evolution-v0.6", "type": "model", "id": model_id,
                            "title": item.get("title", item["statement"][:40]),
                            "date": proposal.get("review_date") or date.today().isoformat(),
                            "event_date": proposal.get("review_date") or date.today().isoformat(),
                            "event_date_precision": "exact", "recorded_at": pos.now(),
                            "source": f"用户确认的 Profile Review {review_id}", "tags": [],
                            "created_at": pos.now(), "updated_at": pos.now()}
                    expected[path] = None
                meta = dict(meta); meta.update({"schema_revision": "profile-evolution-v0.6", "perspective": "system",
                    "evidence_basis": "inferred", "provenance": "ai_observation", "confidence": item["confidence"],
                    "status": item.get("status", "observing"), "evidence": sorted(set(item["evidence"])),
                    "counter_evidence": sorted(set(item.get("counter_evidence", []))), "scope": item.get("scope", []),
                    "user_review_status": item.get("user_review_status", "unreviewed"),
                    "review_checkpoints": list(dict.fromkeys(meta.get("review_checkpoints", []) + [review_id])), "updated_at": pos.now()})
                body += (f"\n\n## System View / {review_id}\n\n{item['statement']}\n\n支持证据：" +
                         ", ".join(f"[[{x}]]" for x in item["evidence"]) + "\n\n反例：" +
                         (", ".join(f"[[{x}]]" for x in item.get("counter_evidence", [])) or "未发现；已执行反例搜索。") +
                         "\n\n适用边界：" + "、".join(item.get("scope", [])))
                pos.check_note(meta, body); staged[path] = pos.dump(meta, body)

            conflicts = []
            for path, wanted in expected.items():
                actual = pos.file_digest(path)
                if actual != wanted: conflicts.append({"path": path.relative_to(self.root).as_posix(), "expected_hash": wanted, "current_hash": actual})
            if conflicts:
                artifact = self.store._save_conflict(review_id, staged, expected, conflicts)
                raise pos.WriteConflict("Profile Review CAS conflict；未覆盖用户内容: " + str(artifact), artifact)
            backups = {p: p.read_text(encoding="utf-8") if p.exists() else None for p in staged}
            written = []
            try:
                for path, text in staged.items(): pos.atomic(path, text); written.append(path)
                validation_after = self.store.validate()
                if not validation_after["valid"]: raise RuntimeError("写入后 validate 失败: " + "; ".join(validation_after["errors"]))
            except BaseException:
                for path in reversed(written):
                    if backups[path] is None: path.unlink(missing_ok=True)
                    else: pos.atomic(path, backups[path])
                raise
        return {"review_id": review_id, "committed": True,
                "files": [p.relative_to(self.root).as_posix() for p in staged],
                "index": self.store.index(), "validation": self.store.validate()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Personal OS Profile Evolution")
    parser.add_argument("--config", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    p = sub.add_parser("prepare"); p.add_argument("question"); p.add_argument("--as-of"); p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("validate-proposal"); p.add_argument("--dossier", required=True, type=Path); p.add_argument("--proposal", required=True, type=Path)
    p = sub.add_parser("commit"); p.add_argument("--dossier", required=True, type=Path); p.add_argument("--proposal", required=True, type=Path); p.add_argument("--accept", required=True); p.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.command == "version": print(json.dumps({"profile_evolution": PROFILE_EVOLUTION_VERSION}, ensure_ascii=False)); return 0
    if args.command == "prepare":
        engine = ProfileEvolution(args.config, True)
        try: output = engine.prepare(args.question, args.as_of)
        finally: engine.close()
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    else:
        dossier = json.loads(args.dossier.read_text(encoding="utf-8")); proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        if args.command == "validate-proposal": output = ProfileEvolution.validate_proposal(proposal, dossier)
        else:
            engine = ProfileEvolution(args.config, False)
            try: output = engine.commit(proposal, dossier, {x for x in args.accept.split(",") if x}, args.confirm)
            finally: engine.close()
    print(json.dumps(output, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
