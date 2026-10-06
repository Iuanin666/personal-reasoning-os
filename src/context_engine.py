"""Personal OS V0.4 read-only Context Engine.

Builds bounded, sourced Context Packs over the existing disposable index.
It never writes canonical Markdown and never generates a final answer.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime
import json
import math
from pathlib import Path
import re
import time
from typing import Any

import yaml

import personal_os as pos

CONTEXT_VERSION = "0.4.1"
ORIGINS = {
    "user_explicit", "behavior_inferred", "ai_observation", "system_record",
    "self_authored", "external_original", "third_party_summary", "ai_summary",
    "personal_reflection",
}
DEFAULT_BUDGET = {
    "core_chars": 3200,
    "personal_chars": 6200,
    "knowledge_chars": 3000,
    "source_evidence_chars": 1800,
    "total_chars": 12000,
    "total_estimated_tokens": 7000,
    "max_excerpt_chars": 760,
    "max_chunks_per_note": 2,
    "max_core_items": 6,
    "max_personal_items": 8,
    "max_knowledge_items": 5,
    "max_source_evidence_items": 4,
}
AUTHORITY = {
    "profile": 0.98, "goal": 0.98, "constraint": 0.98, "principle": 0.96,
    "decision": 0.95, "experience": 0.90, "history": 0.88, "project": 0.86,
    "model": 0.68, "knowledge": 0.75, "source_evidence": 1.0, "system": 0.82,
}
CURRENT_TYPES = {"profile", "goal", "constraint"}
HISTORY_SIGNALS = ("当初", "当时", "过去", "以前", "历史", "为什么选择", "怎么变化")
EVOLUTION_SIGNALS = ("变成现在", "发生了什么变化", "这些年", "这几年", "以前和现在", "为什么会慢慢", "个人画像变化")
CURRENT_SIGNALS = ("现在", "当前", "目前", "如今", "现阶段")
EXTERNAL_SIGNALS = ("书", "论文", "文章", "作者", "原文", "页码", "外部知识", "案例", "研究")


def parse_day(value: Any) -> date | None:
    if value in (None, "", "None"):
        return None
    match = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", str(value))
    if not match:
        return None
    year, month, day = (int(x) if x else 1 for x in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def estimated_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9_]+", text))
    other = max(0, len(text) - cjk - sum(len(x) for x in re.findall(r"[A-Za-z0-9_]+", text)))
    return cjk + math.ceil(words * 1.25) + math.ceil(other / 4)


def infer_task(question: str, task_type: str | None) -> str:
    if task_type and task_type != "auto":
        return task_type
    q = question.casefold()
    if any(x in q for x in EVOLUTION_SIGNALS):
        return "evolution"
    if any(x in q for x in ("选哪个", "怎么选", "决定", "决策")):
        return "decision"
    if any(x in q for x in ("建议", "怎么办")):
        return "advice"
    if any(x in q for x in ("反驳", "批评", "忽略", "盲点")):
        return "critique"
    if any(x in q for x in HISTORY_SIGNALS):
        return "history"
    if any(x in q for x in ("怎么看", "视角")):
        return "perspective"
    return "analysis"


def infer_subject(question: str, subject: str | None) -> str:
    if subject and subject != "auto":
        return subject
    q = question.casefold()
    if any(x in q for x in ("朋友", "同事", "他人", "别人", "伴侣", "家人")):
        return "other"
    if any(x in q for x in ("我", "我的", "自己")):
        return "self"
    return "general"


class ContextEngine:
    def __init__(self, config: Path):
        self.config = Path(config).resolve()
        self.store = pos.Store(self.config, read_only=True)
        self.root = self.store.root
        self._meta: dict[str, dict] = {}

    def close(self):
        for handler in list(self.store.log.handlers):
            handler.close()
            self.store.log.removeHandler(handler)

    def metadata(self, row: dict) -> dict:
        path = row.get("path", "")
        if path in self._meta:
            return self._meta[path]
        if row.get("layer") == "source_evidence":
            value = {"id": row.get("note_id"), "type": "source_evidence",
                     "content_origin": "original", "source_type": "external_original"}
        else:
            try:
                value, _ = pos.parse(self.store.safe(path).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                value = {"id": row.get("note_id"), "type": row.get("type")}
        self._meta[path] = value
        return value

    @staticmethod
    def origin(meta: dict, row: dict) -> str:
        inline = (row.get("text") or "").casefold()
        provenance = str(meta.get("provenance") or "").casefold()
        if "provenance: user_explicit" in inline or provenance == "user_explicit":
            return "user_explicit"
        if provenance == "behavior_inferred":
            return "behavior_inferred"
        if provenance == "ai_observation" or meta.get("type") == "model":
            return "ai_observation"
        content_origin = str(meta.get("content_origin") or "").casefold()
        source_type = str(meta.get("source_type") or "").casefold()
        if row.get("layer") == "source_evidence" or content_origin == "original":
            return "external_original"
        if content_origin == "third_party_summary" or source_type == "third_party_summary":
            return "third_party_summary"
        if content_origin == "ai_summary" or source_type == "ai_summary":
            return "ai_summary"
        if content_origin == "personal_reflection" or source_type == "personal_reflection":
            return "personal_reflection"
        if meta.get("type") == "knowledge" and source_type in {"original_book", "original_paper", "article", "case"}:
            return "external_original"
        if meta.get("type") in {"experience", "decision", "profile", "goal", "constraint", "principle", "history"}:
            return "user_explicit"
        return "system_record"

    @staticmethod
    def effective_day(meta: dict, row: dict) -> date | None:
        note_type = str(meta.get("type") or row.get("type") or "")
        for key in ("event_date", "date", "published_at", "date_added"):
            parsed = parse_day(meta.get(key) or row.get(key))
            if parsed:
                return parsed
        raw = str(meta.get("event_date_raw") or meta.get("date_text") or "")
        match = re.search(r"(20\d{2})", raw)
        if match:
            return date(int(match.group(1)), 1, 1)
        # recorded/created time is not event time for lived events or decisions.
        if note_type not in {"experience", "decision"}:
            return parse_day(meta.get("created_at"))
        return None

    def enrich(self, row: dict, *, as_of: date | None, task: str, subject: str) -> tuple[dict | None, str | None]:
        meta = self.metadata(row)
        note_type = str(meta.get("type") or row.get("type") or "unknown")
        effective = self.effective_day(meta, row)
        if as_of and effective and effective > as_of:
            return None, "after_as_of"
        if as_of and note_type in CURRENT_TYPES:
            return None, "current_snapshot_excluded_by_as_of"
        if task == "history" and note_type in CURRENT_TYPES:
            return None, "current_snapshot_not_past_reason"
        origin = self.origin(meta, row)
        if origin not in ORIGINS:
            origin = "system_record"
        authority = AUTHORITY.get(note_type, 0.70)
        if origin == "ai_observation": authority *= 0.72
        if origin == "third_party_summary": authority *= 0.70
        if origin == "ai_summary": authority *= 0.62
        review_status = meta.get("user_review_status", "unreviewed")
        if review_status == "disagree": authority *= 0.35
        temporal = "historical" if note_type == "history" or task == "history" else "current_or_enduring"
        if as_of:
            temporal = "valid_at_or_before_as_of" if effective else "date_unknown_within_boundary"
        ranking = row.get("ranking") or {}
        reasons = [f"retrieved_from:{row.get('layer')}"]
        if ranking.get("keyword_candidate"): reasons.append("keyword_match")
        if ranking.get("semantic_candidate"): reasons.append("semantic_match")
        if ranking.get("relationship_boost"): reasons.append("explicit_relation")
        reasons.append(f"authority:{authority:.2f}")
        if subject == "other" and row.get("layer") in {"personal", "core"}:
            reasons.append("user_perspective_only_not_other_person_fact")
        if review_status == "disagree": reasons.append("user_explicitly_disagreed_with_system_view")
        excerpt = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()
        return {
            "note_id": row.get("note_id"), "note_type": note_type,
            "title": meta.get("title") or row.get("note_id"),
            "path": row.get("path"), "heading": row.get("heading") or "",
            "layer": row.get("layer"), "temporal_status": temporal,
            "effective_date": effective.isoformat() if effective else None,
            "event_date_precision": meta.get("event_date_precision"),
            "origin": origin, "provenance": meta.get("provenance") or origin,
            "perspective": meta.get("perspective") or ("system" if note_type == "model" else ("self" if note_type == "profile" else None)),
            "evidence_basis": meta.get("evidence_basis") or ("inferred" if note_type == "model" else ("explicit" if note_type == "profile" else None)),
            "user_review_status": review_status,
            "authority": round(authority, 3), "relevance": row.get("score", 0),
            "excerpt": excerpt, "selection_reasons": reasons,
            "subject_scope": "user_history_as_perspective" if subject == "other" and row.get("layer") in {"personal", "core"} else subject,
        }, None

    def diagnostic(self, question: str, layer: str, top_k: int = 16) -> dict:
        if layer == "source_evidence" and pos.requested_page(question):
            return self.store.search_diagnostic(question, mode="hybrid", top_k=top_k,
                                                layer="all", retrieval_profile="optimized_v1")
        return self.store.search_diagnostic(question, mode="hybrid", top_k=top_k,
                                            layer=layer, retrieval_profile="optimized_v1")

    def build(self, question: str, task_type: str = "auto", subject: str = "auto",
              as_of: str | None = None, budget: dict | None = None,
              force_source_evidence: bool = False, debug: bool = False) -> dict:
        started = time.perf_counter()
        task = infer_task(question, task_type)
        who = infer_subject(question, subject)
        cutoff = parse_day(as_of)
        if as_of and not cutoff:
            raise ValueError("as_of 必须是 YYYY、YYYY-MM 或 YYYY-MM-DD")
        limits = DEFAULT_BUDGET | (budget or {})
        explicit_external = any(x in question.casefold() for x in EXTERNAL_SIGNALS)
        external_only = who == "general" and explicit_external
        diagnostics = {}
        if not external_only:
            diagnostics["core"] = self.diagnostic(question, "core")
            diagnostics["personal"] = self.diagnostic(question, "personal")
            if diagnostics["personal"].get("status") == "no_relevant_evidence" and task in {"perspective", "advice", "critique", "decision", "evolution"}:
                fallback_query = {
                    "perspective": "我的历史决策 关注点 权衡 风险 目标 约束",
                    "advice": "我的历史决策 关注点 权衡 结果 风险",
                    "critique": "我的历史决策 结果 反思 失败 盲点",
                    "decision": "我的历史决策 选项 权衡 结果 可逆性",
                    "evolution": "个人状态变化 Profile Review 历史观察 行为模式 变化原因",
                }[task]
                fallback = self.diagnostic(fallback_query, "personal")
                if fallback.get("status") != "no_relevant_evidence":
                    diagnostics["personal"] = fallback
            if task == "evolution":
                targeted = []
                for kind in ("history", "model"):
                    targeted.extend(self.store.search(question, mode="hybrid", top_k=4, layer="personal",
                                                      kind=kind, retrieval_profile="optimized_v1"))
                seen = {x["chunk_id"] for x in targeted}
                diagnostics["personal"]["candidates"] = targeted + [x for x in diagnostics["personal"].get("candidates", []) if x["chunk_id"] not in seen]
                if targeted and diagnostics["personal"].get("status") == "no_relevant_evidence":
                    diagnostics["personal"]["status"] = "weak"
        core_kind = next((kind for signal, kind in (("原则", "principle"), ("目标", "goal"),
                         ("约束", "constraint"), ("限制", "constraint"), ("偏好", "profile"),
                         ("个人状态", "profile")) if signal in question), None)
        if core_kind and "core" in diagnostics:
            targeted = self.store.search(question, mode="hybrid", top_k=4, layer="core",
                                         kind=core_kind, retrieval_profile="optimized_v1")
            known = {x["chunk_id"] for x in diagnostics["core"]["candidates"]}
            diagnostics["core"]["candidates"] = targeted + [x for x in diagnostics["core"]["candidates"] if x["chunk_id"] not in known or x["chunk_id"] not in {y["chunk_id"] for y in targeted}]
        external_requested = any(x in question.casefold() for x in EXTERNAL_SIGNALS) or task in {"advice", "critique", "decision"}
        if external_requested:
            diagnostics["knowledge"] = self.diagnostic(question, "knowledge")
        source_requested = force_source_evidence or pos.source_evidence_intent(question)
        if (explicit_external and not pos.knowledge_overview_intent(question)
                and diagnostics.get("knowledge", {}).get("status") != "supported"):
            source_requested = True
        if source_requested:
            diagnostics["source_evidence"] = self.diagnostic(question, "source_evidence")

        buckets: dict[str, list[dict]] = {"core_context": [], "personal_evidence": [],
                                         "external_knowledge": [], "source_evidence": []}
        map_bucket = {"core": "core_context", "personal": "personal_evidence",
                      "knowledge": "external_knowledge", "source_evidence": "source_evidence"}
        candidates: dict[str, list[dict]] = defaultdict(list)
        excluded = []
        for layer, diagnostic in diagnostics.items():
            if diagnostic.get("status") == "no_relevant_evidence" and not (layer == "source_evidence" and pos.requested_page(question)):
                excluded.extend({"note_id": row.get("note_id"), "heading": row.get("heading"),
                                 "reason": "diagnostic_no_relevant_evidence"}
                                for row in diagnostic.get("candidates", []))
                continue
            for row in diagnostic.get("candidates", []):
                item, reason = self.enrich(row, as_of=cutoff, task=task, subject=who)
                if item:
                    candidates[map_bucket[layer]].append(item)
                else:
                    excluded.append({"note_id": row.get("note_id"), "heading": row.get("heading"), "reason": reason})

        def named_source(item):
            title = str(item.get("title") or "")
            bracketed = re.search(r"《([^》]+)》", title)
            key = bracketed.group(1) if bracketed else title
            return len(key) >= 3 and key in question
        titled = [x for x in candidates["external_knowledge"] if named_source(x)]
        if titled:
            for item in candidates["external_knowledge"]:
                if item not in titled:
                    excluded.append({"note_id": item["note_id"], "heading": item["heading"], "reason": "different_named_source"})
            candidates["external_knowledge"] = titled

        per_budget = {"core_context": limits["core_chars"], "personal_evidence": limits["personal_chars"],
                      "external_knowledge": limits["knowledge_chars"], "source_evidence": limits["source_evidence_chars"]}
        item_caps = {"core_context": limits["max_core_items"], "personal_evidence": limits["max_personal_items"],
                     "external_knowledge": limits["max_knowledge_items"],
                     "source_evidence": limits["max_source_evidence_items"]}
        total_chars = total_tokens = 0
        for bucket_name in ("core_context", "personal_evidence", "external_knowledge", "source_evidence"):
            used = 0
            per_note: dict[str, int] = defaultdict(int)
            for item in candidates[bucket_name]:
                if len(buckets[bucket_name]) >= item_caps[bucket_name]:
                    excluded.append({"note_id": item["note_id"], "heading": item["heading"], "reason": "bucket_item_cap"})
                    continue
                if per_note[item["note_id"]] >= limits["max_chunks_per_note"]:
                    excluded.append({"note_id": item["note_id"], "heading": item["heading"], "reason": "per_note_cap"})
                    continue
                available = min(per_budget[bucket_name] - used, limits["total_chars"] - total_chars,
                                limits["max_excerpt_chars"])
                if available < 80:
                    excluded.append({"note_id": item["note_id"], "heading": item["heading"], "reason": "character_budget"})
                    continue
                excerpt = item["excerpt"][:available]
                token_cost = estimated_tokens(excerpt)
                if total_tokens + token_cost > limits["total_estimated_tokens"]:
                    excluded.append({"note_id": item["note_id"], "heading": item["heading"], "reason": "token_budget"})
                    continue
                item["excerpt"] = excerpt
                item["character_cost"] = len(excerpt)
                item["estimated_token_cost"] = token_cost
                buckets[bucket_name].append(item)
                per_note[item["note_id"]] += 1
                used += len(excerpt); total_chars += len(excerpt); total_tokens += token_cost

        evidence_statuses = [d.get("status") for d in diagnostics.values()]
        substantive = len(buckets["personal_evidence"]) + len(buckets["external_knowledge"]) + len(buckets["source_evidence"])
        if substantive == 0 and all(x == "no_relevant_evidence" for x in evidence_statuses):
            status = "insufficient"
        elif "supported" in evidence_statuses and substantive:
            status = "sufficient"
        else:
            status = "partial"
        missing = []
        if status != "sufficient": missing.append("当前已记录证据不足以直接回答；需要用户补充事实或明确来源。")
        if who == "other": missing.append("缺少他人本人的目标、约束、风险承受能力和可验证事实；用户历史只能作为视角，不能当作他人事实。")
        if cutoff and not buckets["personal_evidence"]:
            missing.append("as_of 边界内没有足够的历史个人证据。")
        if source_requested and not buckets["source_evidence"]:
            missing.append("没有可定位的原文证据；不得把摘要升级为原作者观点。")

        pack = {
            "schema_version": "context-pack-v0.4.1",
            "engine_version": CONTEXT_VERSION,
            "question": question, "task_type": task, "subject": who,
            "as_of": cutoff.isoformat() if cutoff else None,
            "context_status": status,
            **buckets,
            "conflicts": [], "missing_information": missing,
            "provenance_summary": dict(sorted(defaultdict(int, {
                origin: sum(1 for name in buckets for x in buckets[name] if x["origin"] == origin)
                for origin in ORIGINS
            }).items())),
            "budget": limits | {"used_chars": total_chars, "used_estimated_tokens": total_tokens},
            "metrics": {
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "evidence_count": sum(len(x) for x in buckets.values()),
                "diagnostic_status": {k: v.get("status") for k, v in diagnostics.items()},
            },
            "selection_policy": {
                "read_only": True, "retrieval_profile": "optimized_v1",
                "source_evidence": "explicit_or_knowledge_insufficient",
                "current_snapshot_used_for_history": False,
                "evolution_history_on_demand": task == "evolution",
                "other_person_data_is_user_fact": False,
            },
        }
        if debug:
            pack["debug"] = {"excluded_candidates": excluded,
                             "candidate_counts": {k: len(v) for k, v in candidates.items()},
                             "selection_notes": "Reasons are observable routing/ranking facts, not hidden chain-of-thought."}
        return pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Personal OS read-only Context Engine")
    parser.add_argument("--config", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    p = sub.add_parser("build")
    p.add_argument("question")
    p.add_argument("--task-type", default="auto",
                   choices=["auto", "perspective", "analysis", "advice", "critique", "decision", "history", "evolution"])
    p.add_argument("--subject", default="auto", choices=["auto", "self", "other", "general"])
    p.add_argument("--as-of")
    p.add_argument("--source-evidence", action="store_true")
    p.add_argument("--budget-json")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "version":
        print(json.dumps({"context_engine": CONTEXT_VERSION, "read_only": True}, ensure_ascii=False, indent=2))
        return 0
    engine = ContextEngine(args.config)
    try:
        pack = engine.build(args.question, args.task_type, args.subject, args.as_of,
                            json.loads(args.budget_json) if args.budget_json else None,
                            args.source_evidence, args.debug)
    finally:
        engine.close()
    text = json.dumps(pack, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
