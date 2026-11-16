"""End-to-end API flow with the real fixture save (worker run synchronously)."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, start_worker=False)


@pytest.fixture
def client(app):
    return TestClient(app)


def upload(client, campaign_id, files, **form):
    return client.post(f"/campaigns/{campaign_id}/sessions",
                       files=[("files", f) for f in files], data=form)


def test_campaign_endpoints(client):
    r = client.post("/campaigns", json={"name": "Camp", "description": "x"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.post("/campaigns", json={"name": "Camp"}).status_code == 409
    assert client.post("/campaigns", json={"name": ""}).status_code == 422
    assert [c["name"] for c in client.get("/campaigns").json()] == ["Camp"]
    assert client.patch(f"/campaigns/{cid}", json={"name": "Camp 2"}).json()["name"] == "Camp 2"
    assert client.get("/campaigns/999").status_code == 404
    assert upload(client, 999, [("a.eu5", b"x")]).status_code == 404
    assert client.delete(f"/campaigns/{cid}").status_code == 204

    m = client.get("/metrics").json()
    assert {"gold", "population", "regiments", "stability"} <= {x["name"] for x in m["metrics"]}
    assert m["history_metrics"] == ["economical_base", "population", "tax_base"]


def test_full_flow(client, app, mp_save_bytes):
    ingestor = app.state.ingestor
    cid = client.post("/campaigns", json={"name": "MP"}).json()["id"]

    r = upload(client, cid, [("1367.eu5", mp_save_bytes), ("broken.eu5", b"not a save")],
               name="Session 1", played_on="2026-11-15", notes="first")
    assert r.status_code == 202
    body = r.json()
    sid = body["session_id"]
    statuses = {s["file"]: s["status"] for s in body["saves"]}
    assert statuses == {"1367.eu5": "pending", "broken.eu5": "error"}
    save_id = next(s["id"] for s in body["saves"] if s["file"] == "1367.eu5")
    assert "SAV" in client.get(f"/saves/{next(s['id'] for s in body['saves'] if s['file'] == 'broken.eu5')}").json()["error"]

    assert ingestor.process_pending() == 1
    save = client.get(f"/saves/{save_id}").json()
    assert save["status"] == "done" and save["players"] == 14 and save["game_date"] == "1367.1.5"

    # Same save in a second session of the same campaign -> duplicate.
    r = upload(client, cid, [("again.eu5", mp_save_bytes)], name="Session 2")
    assert r.json()["saves"][0]["status"] == "duplicate"
    sid2 = r.json()["session_id"]

    session = client.get(f"/sessions/{sid}").json()
    assert session["name"] == "Session 1" and session["played_on"] == "2026-11-15"
    assert session["saves_by_status"] == {"done": 1, "error": 1}
    assert len(client.get(f"/campaigns/{cid}/sessions").json()) == 2

    camp = client.get(f"/campaigns/{cid}").json()
    assert len(camp["players"]) == 14 and camp["first_date"] == camp["last_date"] == "1367.1.5"
    assert camp["latest"]["Miranda"]["tag"] == "ENG"

    gold = client.get(f"/campaigns/{cid}/series", params={"metric": "gold"}).json()
    assert len(gold["points"]) == 14 and all(len(v) == 1 for v in gold["points"].values())
    one = client.get(f"/campaigns/{cid}/series", params={"metric": "locations", "player": "Miranda", "session": sid})
    assert one.json()["points"] == {"Miranda": [["1367.1.5", 157.0]]}
    assert client.get(f"/campaigns/{cid}/series", params={"metric": "nope"}).status_code == 422

    summary = client.get(f"/sessions/{sid}/summary").json()
    assert summary["players"]["Miranda"]["locations"] == {"start": 157.0, "end": 157.0, "delta": 0.0}

    timeline = client.get(f"/campaigns/{cid}/players/Miranda").json()["timeline"]
    assert timeline[0]["tag"] == "ENG" and timeline[0]["metrics"]["locations"] == 157
    assert client.get(f"/campaigns/{cid}/players/Nobody").status_code == 404

    hist = client.get(f"/campaigns/{cid}/history", params={"metric": "population"}).json()
    assert len(hist["series"]["ENG"]) == 31 and hist["players"]["ENG"] == ["Miranda"]
    assert client.get(f"/campaigns/{cid}/history", params={"metric": "gold"}).status_code == 422

    # Reprocess.
    assert client.post(f"/saves/{save_id}/reprocess").json() == {"queued": 1}
    assert ingestor.process_pending() == 1
    assert client.get(f"/saves/{save_id}").json()["status"] == "done"

    # Same file in another campaign is processed independently; the stored file is shared.
    cid2 = client.post("/campaigns", json={"name": "Other"}).json()["id"]
    r = upload(client, cid2, [("1367.eu5", mp_save_bytes)])
    assert r.json()["saves"][0]["status"] == "pending"
    sid3 = r.json()["session_id"]
    upload_file = ingestor.path_for(client.get(f"/saves/{save_id}").json()["sha256"])

    # Deleting: campaign with sessions -> 409; deleting sessions removes their data.
    assert client.delete(f"/campaigns/{cid}").status_code == 409
    assert client.delete(f"/sessions/{sid}").status_code == 204
    assert client.delete(f"/sessions/{sid2}").status_code == 204
    assert client.get(f"/campaigns/{cid}").json()["players"] == []
    assert upload_file.exists()  # still referenced by campaign "Other"
    assert client.delete(f"/campaigns/{cid}").status_code == 204
    assert client.delete(f"/sessions/{sid3}").status_code == 204
    assert not upload_file.exists()
