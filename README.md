# Trinity Health learning platform: working code

- scoring/   score.py scores a transcript against rubric.json (schema.json validates the output). Sample transcript included.
- persona/   chat.py is a text-only practice chat with Dr. Priya Raman (persona.json, persona_prompt.txt).

Setup:  pip install anthropic jsonschema   then   export ANTHROPIC_API_KEY=...
Try:    cd persona && python chat.py --mock          (no key needed)
        python chat.py --pushback tough              (real model)
        python ../scoring/score.py transcript.txt    (score what you just said)
Spec:   see claude/trinity-learning-platform-spec.md in the General BS project.
The clickable prototype lives in the published design artifact.

## service/ (session service)
FastAPI + SQLite. Ties persona chat, scoring and the database together; the avatar plugs in through service/avatar.py.
  pip install -r requirements.txt
  cd service && python -m pytest -q                 (5 tests, mock mode, no key)
  MOCK=1 uvicorn app:app --reload                   (no key)   |   uvicorn app:app   (needs ANTHROPIC_API_KEY)
Endpoints: POST /sessions, POST /sessions/{id}/turn, POST /sessions/{id}/end (scores, idempotent), GET /sessions/{id}, GET /admin/aggregate (groups under 10 learners hidden).
TavusAdapter is a stub: fill in after checking current Tavus docs. It refuses to start a replica with no consent record.
