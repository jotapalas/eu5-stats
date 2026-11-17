"""End-to-end API flow with the real fixture save (worker run synchronously).

Expected values are derived from the save, so any EU5 multiplayer save works as the fixture."""
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
    names = {x["name"] for x in m["metrics"]}
    assert {"gold", "population", "vassals", "all_vassals", "stability"} <= names
    assert not {"armies", "navies", "regiments"} & names
    assert m["vassal_metrics"]["population"] == {"direct": "population__vassals", "all": "population__all_vassals"}
    assert set(m["vassal_metrics"]) <= names


def test_full_flow(client, app, mp_save_bytes, mp_stats, mp_played, mp_ai):
    """Expectations come from the extraction of the same save (`mp_stats`), not from fixed values."""
    ingestor = app.state.ingestor
    ref, removed = mp_played[0], mp_played[1]  # reference country, played country to stop tracking
    n_countries = len(mp_stats.countries)
    n_players = sum(len(c.players) for c in mp_stats.countries)
    date, tag, loc = mp_stats.game_date, ref.tag, ref.metrics["locations"]
    cid = client.post("/campaigns", json={"name": "MP"}).json()["id"]

    r = upload(client, cid, [("save.eu5", mp_save_bytes), ("broken.eu5", b"not a save")],
               name="Session 1", played_on="2026-11-15", notes="first")
    assert r.status_code == 202
    body = r.json()
    sid = body["session_id"]
    statuses = {s["file"]: s["status"] for s in body["saves"]}
    assert statuses == {"save.eu5": "pending", "broken.eu5": "error"}
    save_id = next(s["id"] for s in body["saves"] if s["file"] == "save.eu5")
    assert "SAV" in client.get(f"/saves/{next(s['id'] for s in body['saves'] if s['file'] == 'broken.eu5')}").json()["error"]

    assert ingestor.process_pending() == 1
    save = client.get(f"/saves/{save_id}").json()
    assert save["status"] == "done" and save["game_date"] == date
    assert (save["countries"], save["players"]) == (n_countries, n_players)

    # Same save in a second session of the same campaign -> duplicate.
    r = upload(client, cid, [("again.eu5", mp_save_bytes)], name="Session 2")
    assert r.json()["saves"][0]["status"] == "duplicate"
    sid2 = r.json()["session_id"]

    session = client.get(f"/sessions/{sid}").json()
    assert session["name"] == "Session 1" and session["played_on"] == "2026-11-15"
    assert session["saves_by_status"] == {"done": 1, "error": 1}
    assert len(client.get(f"/campaigns/{cid}/sessions").json()) == 2

    camp = client.get(f"/campaigns/{cid}").json()
    assert sorted(camp["countries"]) == sorted(c.tag for c in mp_stats.countries)
    assert camp["first_date"] == camp["last_date"] == date
    assert camp["latest"][tag]["players"] == ref.players
    assert camp["latest"][tag]["metrics"] == ref.metrics

    gold = client.get(f"/campaigns/{cid}/series", params={"metric": "gold"}).json()
    assert len(gold["points"]) == n_countries and all(len(v) == 1 for v in gold["points"].values())
    one = client.get(f"/campaigns/{cid}/series", params={"metric": "locations", "tag": tag.lower(), "session": sid})
    assert one.json()["points"] == {tag: [[date, loc]]}
    assert client.get(f"/campaigns/{cid}/series", params={"metric": "nope"}).status_code == 422
    agg = client.get(f"/campaigns/{cid}/series", params={"metric": "locations__all_vassals", "tag": tag})
    assert agg.json()["points"] == {tag: [[date, ref.metrics["locations__all_vassals"]]]}

    summary = client.get(f"/sessions/{sid}/summary").json()
    assert summary["countries"][tag]["locations"] == {"start": loc, "end": loc, "delta": 0.0}

    country = client.get(f"/campaigns/{cid}/countries/{tag}").json()
    assert (country["tag"], country["country_id"]) == (tag, ref.country_id)
    assert country["timeline"][0]["players"] == ref.players and country["timeline"][0]["metrics"] == ref.metrics
    assert client.get(f"/campaigns/{cid}/countries/XXX").status_code == 404

    # Tracked list: add an AI country and drop a played one; reprocessing applies the current list.
    ai = mp_ai.tag
    assert client.post(f"/campaigns/{cid}/countries", json={"tag": ai.lower()}).json()["country_id"] is None
    assert client.post(f"/campaigns/{cid}/countries", json={"tag": ai}).status_code == 409
    assert client.post(f"/campaigns/{cid}/countries", json={"tag": "no way"}).status_code == 422
    assert client.delete(f"/campaigns/{cid}/countries/{removed.tag}").status_code == 204
    assert client.delete(f"/campaigns/{cid}/countries/{removed.tag}").status_code == 404
    assert client.post(f"/saves/{save_id}/reprocess").json() == {"queued": 1}
    assert ingestor.process_pending() == 1
    save = client.get(f"/saves/{save_id}").json()
    assert save["status"] == "done"
    assert (save["countries"], save["players"]) == (n_countries, n_players - len(removed.players))
    countries = {c["tag"]: c for c in client.get(f"/campaigns/{cid}/countries").json()}
    assert countries[ai]["country_id"] == mp_ai.country_id and countries[ai]["players"] == []
    assert not countries[removed.tag]["active"]
    assert removed.tag not in client.get(f"/campaigns/{cid}").json()["latest"]

    # Main player: shown campaign-wide, while snapshots keep the save's name.
    r = client.patch(f"/campaigns/{cid}/countries/{tag.lower()}", json={"player": "Main"})
    assert r.status_code == 200 and r.json()["player"] == "Main"
    camp = client.get(f"/campaigns/{cid}").json()
    assert camp["main_players"] == {tag: "Main"} and camp["latest"][tag]["players"] == ref.players
    assert client.patch(f"/campaigns/{cid}/countries/{tag}", json={"player": None}).json()["player"] is None
    assert client.patch(f"/campaigns/{cid}/countries/XXX", json={"player": "x"}).status_code == 404

    # Same file in another campaign is processed independently; the stored file is shared.
    cid2 = client.post("/campaigns", json={"name": "Other"}).json()["id"]
    r = upload(client, cid2, [("save.eu5", mp_save_bytes)])
    assert r.json()["saves"][0]["status"] == "pending"
    sid3 = r.json()["session_id"]
    upload_file = ingestor.path_for(client.get(f"/saves/{save_id}").json()["sha256"])

    # Deleting: campaign with sessions -> 409; deleting sessions removes their data.
    assert client.delete(f"/campaigns/{cid}").status_code == 409
    assert client.delete(f"/sessions/{sid}").status_code == 204
    assert client.delete(f"/sessions/{sid2}").status_code == 204
    assert client.get(f"/campaigns/{cid}").json()["latest"] == {}
    assert upload_file.exists()  # still referenced by campaign "Other"
    assert client.delete(f"/campaigns/{cid}").status_code == 204
    assert client.delete(f"/sessions/{sid3}").status_code == 204
    assert not upload_file.exists()
