"""Personal OS V0.5 read-only analysis planner.

The current AI client performs prose reasoning from this sourced plan. This
module routes the mode and supplies a bounded Context Pack; it never writes.
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
from context_engine import ContextEngine, infer_subject

ANALYZE_VERSION="0.5.1"

def infer_mode(question:str, requested:str="auto") -> str:
    if requested!="auto": return requested
    q=question.casefold()
    if any(x in q for x in ("选哪个","怎么选","到底应该","做决定","是否应该")): return "decision"
    if any(x in q for x in ("盲点","忽略","批评","反驳","挑战我的","挑战一下","专门挑战")): return "critique"
    if any(x in q for x in ("建议","怎么办","给他","给她")): return "advice"
    if any(x in q for x in ("按照我的思维","我的视角","我会怎么看","会怎么看","如果是我","像我一样看")): return "perspective"
    return "analysis"

def make_plan(config:Path,question:str,mode:str="auto",subject:str="auto",as_of:str|None=None,debug=False) -> dict:
    started=time.perf_counter(); selected=infer_mode(question,mode); who=infer_subject(question,subject)
    engine=ContextEngine(config)
    try: pack=engine.build(question,selected,who,as_of,debug=debug)
    finally: engine.close()
    required=["问题定义","你的历史视角","当前情况与过去的不同","缺失信息 / 不确定性","AI 分析 / 挑战","Evidence / Source Notes"]
    if pack["external_knowledge"]: required.insert(3,"外部知识 / 案例")
    if selected=="decision": required += ["选项与权衡","可逆性与下行风险","建议与置信度"]
    if selected=="critique": required += ["反例与可能忽略的因素"]
    return {
      "schema_version":"analyze-plan-v0.5.1","analyze_version":ANALYZE_VERSION,
      "question":question,"mode":selected,"subject":who,"as_of":as_of,
      "analysis_status":"needs_information" if pack["context_status"] in {"partial","insufficient"} else "ready",
      "context_pack":pack,
      "response_contract":{
        "required_semantic_sections":required,
        "voices":{
          "historical_perspective":"Only claims supported by personal/core evidence; cite note_id and heading.",
          "external_evidence":"Preserve external_original / third_party_summary / ai_summary / personal_reflection labels.",
          "ai_analysis_challenge":"Clearly label present synthesis as AI analysis, not a previously stated user belief."
        },
        "subject_rule":"For other, user history is a perspective lens only; never assert it as the other person's facts.",
        "anti_lock_in":["compare current situation with past","check outcomes","name changed goals or constraints","seek counterexamples","state missing information"],
        "insufficiency_rule":"Ask for missing facts or abstain from personalized claims when context_status is insufficient.",
        "profile_language_rule":"Calibrate wording to evidence: repeated cross-context evidence may use 'repeatedly shown'; medium evidence uses 'appears to tend'; low evidence uses 'a possible pattern'. Never say essentially/always. A disagreed System View must be described as a historical observation the user disputes.",
        "citations":"Use note_id + heading; quote source evidence only when its locator is present.",
        "hidden_reasoning":"Do not expose or persist chain-of-thought; provide concise evidence-linked rationale only.",
        "write_policy":"read_only; candidate observations remain ephemeral until an explicit later $reflect request"
      },
      "candidate_observations":[],
      "metrics":{"context_latency_ms":pack["metrics"]["latency_ms"],"planning_wall_time_ms":round((time.perf_counter()-started)*1000,2),"evidence_count":pack["metrics"]["evidence_count"],"context_chars":pack["budget"]["used_chars"]}
    }

def main():
    p=argparse.ArgumentParser(description="Personal OS read-only analysis planner");p.add_argument("--config",required=True,type=Path)
    sub=p.add_subparsers(dest="command",required=True);sub.add_parser("version")
    x=sub.add_parser("plan");x.add_argument("question");x.add_argument("--mode",default="auto",choices=["auto","perspective","analysis","advice","critique","decision"]);x.add_argument("--subject",default="auto",choices=["auto","self","other","general"]);x.add_argument("--as-of");x.add_argument("--debug",action="store_true");x.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.command=="version": print(json.dumps({"analyze":ANALYZE_VERSION,"read_only":True},ensure_ascii=False,indent=2));return 0
    result=make_plan(a.config,a.question,a.mode,a.subject,a.as_of,a.debug); text=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text,encoding="utf-8")
    else:print(text,end="")
    return 0
if __name__=="__main__":raise SystemExit(main())
