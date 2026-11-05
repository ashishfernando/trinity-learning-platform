#!/usr/bin/env python3
"""Score a practice-conversation transcript against a rubric.

Usage:
  python score.py transcript.txt [--rubric rubric.json] [--runs 2] [--mock]

Needs ANTHROPIC_API_KEY unless --mock. Model: env SCORER_MODEL (default claude-sonnet-5-5).
Transcript lines: "[mm:ss] Learner: text" or "[mm:ss] Character: text".
"""
import argparse, json, os, re, sys
from pathlib import Path
from jsonschema import validate, ValidationError

HERE = Path(__file__).parent
PROMPT_VERSION = "score-v1"
SYSTEM = """You are an expert assessor of leadership conversations in healthcare. You will receive a rubric and a transcript of a practice conversation between a Learner and a Character. Score only what the Learner said. Do not reward length or polish. Do not penalize the Learner for the Character's behavior.

Rules
- Score each criterion 0 to 100 using the anchors in the rubric.
- Every score must cite at least one verbatim quote from the Learner with its timestamp. If there is no evidence, score low and say so.
- Give one concrete, specific suggestion per criterion. No generic advice.
- Pick up to 2 "strong" moments and up to 2 "improve" moments to replay.
- Do not infer the Learner's identity, health, or traits. Judge the transcript only.
- If the transcript mentions what looks like real patient information, add "possible_phi_mentioned" to flags.
- Return JSON only, matching the schema. No prose outside the JSON."""

LINE = re.compile(r"^\[(\d{1,2}:\d{2})\]\s*(Learner|Character):\s*(.+)$")

def parse(text):
    turns = []
    for ln in text.splitlines():
        m = LINE.match(ln.strip())
        if m:
            turns.append({"t": m.group(1), "speaker": m.group(2), "text": m.group(3)})
    if not turns:
        sys.exit("No transcript lines found. Expected '[mm:ss] Learner: ...'")
    return turns

def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip()

def call_model(rubric, schema, transcript_text, mock, runs_idx):
    if mock:
        return {
            "summary": "You moved from a questioning start to a clear commitment. Open with purpose before questions.",
            "criteria": [
                {"id": "opens_with_purpose", "score": 60 + runs_idx * 2, "evidence": [{"t": "00:20", "quote": "Can you walk me through what happened with the unit staffing last quarter?"}], "feedback": "Lead with one sentence on why this conversation matters to them."},
                {"id": "listens_reflects", "score": 86, "evidence": [{"t": "01:18", "quote": "That matters to me."}], "feedback": "Reflect their phrase back, then ask the open question."},
                {"id": "holds_line", "score": 84, "evidence": [{"t": "00:45", "quote": "Nothing is final, and I should have brought you in sooner."}], "feedback": "State what is decided as well as what is open."},
                {"id": "next_step", "score": 90, "evidence": [{"t": "02:02", "quote": "I'll send the written plan by Friday"}], "feedback": "Confirm who attends the 90-day review."}
            ],
            "moments": [
                {"kind": "strong", "t": "01:18", "quote": "What would we need to protect for those patients if the unit does consolidate?", "why": "Open question that moves toward a solution."},
                {"kind": "improve", "t": "00:20", "quote": "Thanks for coming in.", "why": "Opening ignored the concern the Character was carrying."}
            ],
            "values": [{"name": "Stewardship", "level": "developing"}],
            "confidence": "medium",
            "flags": []
        }
    import anthropic
    client = anthropic.Anthropic()
    user = ("RUBRIC:\n" + json.dumps(rubric, indent=2) + "\n\nSCENARIO: " + rubric.get("scenario", "") +
            "\n\nOUTPUT JSON SCHEMA:\n" + json.dumps(schema) + "\n\nTRANSCRIPT:\n" + transcript_text)
    msg = client.messages.create(model=os.environ.get("SCORER_MODEL", "claude-sonnet-5-5"),
                                 max_tokens=3000, system=SYSTEM,
                                 messages=[{"role": "user", "content": user}])
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)

def score_once(rubric, schema, transcript_text, mock, idx):
    last_err = None
    for _ in range(2):  # retry once on invalid output
        try:
            out = call_model(rubric, schema, transcript_text, mock, idx)
            validate(out, schema)
            return out
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
    sys.exit(f"Model output failed validation twice: {last_err}")

def check_quotes(result, turns):
    learner = norm(" ".join(t["text"] for t in turns if t["speaker"] == "Learner"))
    bad = []
    quotes = [e["quote"] for c in result["criteria"] for e in c["evidence"]] + [m["quote"] for m in result["moments"]]
    for q in quotes:
        if norm(q) not in learner:
            bad.append(q)
    return bad

def finalize(result, rubric, turns):
    weights = {c["id"]: c.get("weight", 1) for c in rubric["criteria"]}
    ids = set(weights)
    got = {c["id"] for c in result["criteria"]}
    flags = list(result["flags"])
    if got != ids:
        flags.append("criteria_mismatch")
    num = sum(c["score"] * weights.get(c["id"], 0) for c in result["criteria"])
    den = sum(weights.get(c["id"], 0) for c in result["criteria"]) or 1
    result["overall"] = round(num / den)   # computed in code, not by the model
    if check_quotes(result, turns):
        flags.append("unverified_quote")
    if len(turns) < 6:
        flags.append("short_session")
    result["flags"] = sorted(set(flags))
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--rubric", default=str(HERE / "rubric.json"))
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if not a.mock and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY, or use --mock to test the pipeline.")
    rubric = json.loads(Path(a.rubric).read_text())
    schema = json.loads((HERE / "schema.json").read_text())
    text = Path(a.transcript).read_text()
    turns = parse(text)
    results = [finalize(score_once(rubric, schema, text, a.mock, i), rubric, turns) for i in range(a.runs)]
    final = results[0]
    if len(results) > 1:
        spread = max(r["overall"] for r in results) - min(r["overall"] for r in results)
        final["run_scores"] = [r["overall"] for r in results]
        if spread > 8:
            final["flags"] = sorted(set(final["flags"] + ["needs_human_review"]))
    final["meta"] = {"prompt_version": PROMPT_VERSION, "rubric": rubric["id"], "mock": a.mock,
                     "model": "mock" if a.mock else os.environ.get("SCORER_MODEL", "claude-sonnet-5-5")}
    print(json.dumps(final, indent=2))

if __name__ == "__main__":
    main()
