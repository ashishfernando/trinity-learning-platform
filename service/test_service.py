"""Run:  cd service && python -m pytest -q     (uses mock mode and a temp database)"""
import os, tempfile
os.environ["MOCK"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
import app as svc

client = TestClient(svc.app)

def run_session():
    sid = client.post("/sessions", json={"person_id": 1, "scenario_id": 1, "pushback": "realistic"}).json()["session_id"]
    for line in ["Nothing is final, and I should have brought you in sooner. Tell me what you are seeing.",
                 "What would we need to protect for those patients?",
                 "I can commit to the navigator and transport plan and a review in 90 days. I will send the plan by Friday."]:
        r = client.post(f"/sessions/{sid}/turn", json={"text": line}).json()
    return sid, r

def test_full_flow():
    sid, last = run_session()
    assert last["ended"] is True
    card = client.post(f"/sessions/{sid}/end").json()
    assert 0 <= card["overall"] <= 100 and card["meta"]["model"] == "mock"
    again = client.post(f"/sessions/{sid}/end").json()
    assert again["overall"] == card["overall"]          # idempotent
    got = client.get(f"/sessions/{sid}").json()
    assert got["transcript"][0]["speaker"] == "Character" and got["score"] is not None

def test_turn_after_end_rejected():
    sid, _ = run_session()
    assert client.post(f"/sessions/{sid}/turn", json={"text": "hi"}).status_code == 409

def test_bad_input():
    assert client.post("/sessions", json={"person_id": 1, "scenario_id": 1, "pushback": "nasty"}).status_code == 422
    assert client.post("/sessions", json={"person_id": 99, "scenario_id": 1}).status_code == 404
    assert client.get("/sessions/9999").status_code == 404

def test_small_groups_hidden():
    sid, _ = run_session(); client.post(f"/sessions/{sid}/end")
    g = client.get("/admin/aggregate").json()["groups"][0]
    assert g["hidden"] is True and "avg_overall" not in g

def test_no_replica_without_consent():
    import pytest
    from avatar import TavusAdapter
    with pytest.raises(ValueError):
        TavusAdapter().start({"replica_id": "r1"}, "", 1)
