"""Session service. Run:  MOCK=1 uvicorn app:app --reload     (MOCK=1 needs no API key)
Env: DB_PATH (default trinity.db), MOCK, AVATAR (text|tavus), PERSONA_MODEL, SCORER_MODEL, MIN_GROUP (default 10)
"""
import json, os, sqlite3, sys, time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "persona"))
sys.path.insert(0, str(ROOT / "scoring"))
import chat as persona_chat      # build_prompt, mock_reply, model_reply, END
import score as scorer           # score_once, finalize, PROMPT_VERSION
from avatar import get_adapter

HERE = Path(__file__).parent
MOCK = os.environ.get("MOCK") == "1"
MIN_GROUP = int(os.environ.get("MIN_GROUP", "10"))
SCHEMA = json.loads((ROOT / "scoring" / "schema.json").read_text())

def db():
    path = os.environ.get("DB_PATH", str(HERE / "trinity.db"))
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init():
    c = db()
    c.executescript((HERE / "schema.sql").read_text())
    if not c.execute("SELECT 1 FROM role").fetchone():   # seed from the prototype
        pj = json.loads((ROOT / "persona" / "persona.json").read_text())
        rubric = (ROOT / "scoring" / "rubric.json").read_text()
        c.execute("INSERT INTO role(id,title) VALUES (1,'Ministry Market CEO')")
        c.execute("INSERT INTO person(id,name,role_id,setting) VALUES (1,'Demo Learner',1,'Hospital')")
        c.execute("INSERT INTO persona(id,name,role,setting,learner_title,situation,goal,worries,opening_stance,opening_line) VALUES (1,?,?,?,?,?,?,?,?,?)",
                  (pj["name"], pj["role"], pj["setting"], pj["learner_title"], pj["situation"], pj["goal"], pj["worries"], pj["opening_stance"], pj["opening_line"]))
        c.execute("INSERT INTO scenario(id,role_id,title,persona_id,pass_mark,rubric_json) VALUES (1,1,'Consolidating a service with a skeptical physician leader',1,70,?)", (rubric,))
    c.commit(); c.close()

def audit(c, actor, action, obj):
    c.execute("INSERT INTO audit_event(actor,action,object,at) VALUES (?,?,?,?)", (actor, action, obj, time.time()))

app = FastAPI(title="Trinity learning platform: session service")
init()

class StartReq(BaseModel):
    person_id: int
    scenario_id: int
    pushback: str = "realistic"

class TurnReq(BaseModel):
    text: str

def load_session(c, sid):
    s = c.execute("SELECT * FROM session WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "No such session")
    return s

def persona_for(c, scenario_id):
    row = c.execute("SELECT p.* FROM persona p JOIN scenario s ON s.persona_id=p.id WHERE s.id=?", (scenario_id,)).fetchone()
    if not row:
        raise HTTPException(404, "No such scenario")
    return dict(row)

def fmt_t(ms):
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"

@app.post("/sessions")
def start(req: StartReq):
    if req.pushback not in ("supportive", "realistic", "tough"):
        raise HTTPException(422, "pushback must be supportive, realistic or tough")
    c = db()
    if not c.execute("SELECT 1 FROM person WHERE id=?", (req.person_id,)).fetchone():
        raise HTTPException(404, "No such person")
    p = persona_for(c, req.scenario_id)
    now = time.time()
    cur = c.execute("INSERT INTO session(person_id,scenario_id,pushback,started_at) VALUES (?,?,?,?)", (req.person_id, req.scenario_id, req.pushback, now))
    sid = cur.lastrowid
    system = persona_chat.build_prompt(p, req.pushback)
    conv = get_adapter(os.environ.get("AVATAR", "text")).start(p, system, sid)
    c.execute("UPDATE session SET avatar_conversation_id=? WHERE id=?", (conv, sid))
    c.execute("INSERT INTO transcript_turn(session_id,t_ms,speaker,text) VALUES (?,?,?,?)", (sid, 0, "Character", p["opening_line"]))
    audit(c, f"person:{req.person_id}", "session_start", f"session:{sid}")
    c.commit(); c.close()
    return {"session_id": sid, "character": p["name"], "opening_line": p["opening_line"]}

@app.post("/sessions/{sid}/turn")
def turn(sid: int, req: TurnReq):
    c = db()
    s = load_session(c, sid)
    if s["ended_at"]:
        raise HTTPException(409, "Session already ended")
    text = req.text.strip()
    if not text:
        raise HTTPException(422, "Empty turn")
    t_ms = int((time.time() - s["started_at"]) * 1000)
    c.execute("INSERT INTO transcript_turn(session_id,t_ms,speaker,text) VALUES (?,?,?,?)", (sid, t_ms, "Learner", text))
    rows = c.execute("SELECT speaker,text FROM transcript_turn WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    history = [{"role": "user" if r["speaker"] == "Learner" else "assistant", "content": r["text"]} for r in rows]
    p = persona_for(c, s["scenario_id"])
    if MOCK:
        reply = persona_chat.mock_reply(history, p)
    else:
        system = persona_chat.build_prompt(p, s["pushback"])
        msgs = [{"role": "user", "content": "(The conversation begins. You speak first.)"}] + history
        reply = persona_chat.model_reply(system, msgs)
    ended = persona_chat.END in reply
    reply = reply.replace(persona_chat.END, "").strip()
    c.execute("INSERT INTO transcript_turn(session_id,t_ms,speaker,text) VALUES (?,?,?,?)", (sid, int((time.time() - s["started_at"]) * 1000), "Character", reply))
    if ended:
        c.execute("UPDATE session SET ended_at=? WHERE id=?", (time.time(), sid))
    c.commit(); c.close()
    return {"reply": reply, "ended": ended}

@app.post("/sessions/{sid}/end")
def end(sid: int):
    """Close the session if open, score it (idempotent), and return the scorecard JSON."""
    c = db()
    s = load_session(c, sid)
    done = c.execute("SELECT result_json FROM score WHERE session_id=?", (sid,)).fetchone()
    if done:
        return json.loads(done["result_json"])
    if not s["ended_at"]:
        c.execute("UPDATE session SET ended_at=? WHERE id=?", (time.time(), sid))
    rows = c.execute("SELECT t_ms,speaker,text FROM transcript_turn WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    turns = [{"t": fmt_t(r["t_ms"]), "speaker": r["speaker"], "text": r["text"]} for r in rows]
    text = "\n".join(f"[{t['t']}] {t['speaker']}: {t['text']}" for t in turns)
    rubric = json.loads(c.execute("SELECT rubric_json FROM scenario WHERE id=?", (s["scenario_id"],)).fetchone()["rubric_json"])
    results = [scorer.finalize(scorer.score_once(rubric, SCHEMA, text, MOCK, i), rubric, turns) for i in range(2)]
    final = results[0]
    final["run_scores"] = [r["overall"] for r in results]
    review = max(final["run_scores"]) - min(final["run_scores"]) > 8
    if review:
        final["flags"] = sorted(set(final["flags"] + ["needs_human_review"]))
    model = "mock" if MOCK else os.environ.get("SCORER_MODEL", "claude-sonnet-5-5")
    final["meta"] = {"prompt_version": scorer.PROMPT_VERSION, "rubric": rubric["id"], "model": model}
    c.execute("INSERT INTO score(session_id,overall,result_json,model,prompt_version,rubric_id,needs_review,created_at) VALUES (?,?,?,?,?,?,?,?)",
              (sid, final["overall"], json.dumps(final), model, scorer.PROMPT_VERSION, rubric["id"], int(review), time.time()))
    audit(c, "system", "session_scored", f"session:{sid}")
    c.commit(); c.close()
    return final

@app.get("/sessions/{sid}")
def get_session(sid: int):
    c = db()
    s = load_session(c, sid)
    rows = c.execute("SELECT t_ms,speaker,text FROM transcript_turn WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    sc = c.execute("SELECT result_json FROM score WHERE session_id=?", (sid,)).fetchone()
    return {"session": dict(s), "transcript": [{"t": fmt_t(r["t_ms"]), "speaker": r["speaker"], "text": r["text"]} for r in rows],
            "score": json.loads(sc["result_json"]) if sc else None}

@app.get("/admin/aggregate")
def aggregate():
    """Per-role averages. Groups smaller than MIN_GROUP learners are hidden."""
    c = db()
    rows = c.execute("""SELECT r.title AS role, COUNT(DISTINCT se.person_id) AS learners, COUNT(*) AS sessions, AVG(sc.overall) AS avg_overall
        FROM score sc JOIN session se ON se.id=sc.session_id JOIN person p ON p.id=se.person_id JOIN role r ON r.id=p.role_id GROUP BY r.id""").fetchall()
    out = []
    for r in rows:
        if r["learners"] < MIN_GROUP:
            out.append({"role": r["role"], "hidden": True, "reason": f"fewer than {MIN_GROUP} learners"})
        else:
            out.append({"role": r["role"], "learners": r["learners"], "sessions": r["sessions"], "avg_overall": round(r["avg_overall"])})
    return {"groups": out}
