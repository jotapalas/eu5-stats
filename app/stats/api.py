"""JSON API for campaigns, sessions, saves and statistics."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from .db import Store
from .ingest import Ingestor
from .metrics import HISTORY_FIELDS, METRICS, METRICS_BY_NAME

router = APIRouter()
HISTORY_METRICS = sorted(HISTORY_FIELDS.values())


def _store(request: Request) -> Store:
    return request.app.state.store


def _ingestor(request: Request) -> Ingestor:
    return request.app.state.ingestor


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class CountryIn(BaseModel):
    tag: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z0-9_]+$")


# ---------------------------------------------------------------------- metrics
@router.get("/metrics", tags=["stats"])
def list_metrics() -> dict:
    return {
        "metrics": [{"name": m.name, "category": m.category, "description": m.description} for m in METRICS],
        "history_metrics": HISTORY_METRICS,
    }


# ---------------------------------------------------------------------- campaigns
@router.post("/campaigns", status_code=201, tags=["campaigns"])
def create_campaign(body: CampaignIn, request: Request) -> dict:
    return _store(request).create_campaign(body.name, body.description)


@router.get("/campaigns", tags=["campaigns"])
def list_campaigns(request: Request) -> list[dict]:
    return _store(request).list_campaigns()


@router.get("/campaigns/{campaign_id}", tags=["campaigns"])
def get_campaign(campaign_id: int, request: Request) -> dict:
    store = _store(request)
    out = store.get_campaign(campaign_id)
    out["latest"] = store.latest_snapshots(campaign_id)
    return out


@router.patch("/campaigns/{campaign_id}", tags=["campaigns"])
def update_campaign(campaign_id: int, body: CampaignPatch, request: Request) -> dict:
    return _store(request).update_campaign(campaign_id, body.name, body.description)


@router.delete("/campaigns/{campaign_id}", status_code=204, tags=["campaigns"])
def delete_campaign(campaign_id: int, request: Request):
    _store(request).delete_campaign(campaign_id)


# ---------------------------------------------------------------------- tracked countries
@router.get("/campaigns/{campaign_id}/countries", tags=["countries"])
def list_countries(campaign_id: int, request: Request) -> list[dict]:
    return _store(request).list_countries(campaign_id)


@router.post("/campaigns/{campaign_id}/countries", status_code=201, tags=["countries"])
def add_country(campaign_id: int, body: CountryIn, request: Request) -> dict:
    """Track a country in saves processed from now on (use /reprocess for existing saves)."""
    return _store(request).add_country(campaign_id, body.tag.upper())


@router.delete("/campaigns/{campaign_id}/countries/{tag}", status_code=204, tags=["countries"])
def remove_country(campaign_id: int, tag: str, request: Request):
    """Stop tracking a country in saves processed from now on; extracted data is kept."""
    _store(request).remove_country(campaign_id, tag.upper())


@router.get("/campaigns/{campaign_id}/countries/{tag}", tags=["countries"])
def country(campaign_id: int, tag: str, request: Request) -> dict:
    return _store(request).country_timeline(campaign_id, tag.upper())


@router.post("/campaigns/{campaign_id}/reprocess", status_code=202, tags=["campaigns"])
def reprocess_campaign(campaign_id: int, request: Request) -> dict:
    n = _store(request).mark_pending(campaign_id=campaign_id)
    _ingestor(request).notify()
    return {"queued": n}


# ---------------------------------------------------------------------- sessions
@router.post("/campaigns/{campaign_id}/sessions", status_code=202, tags=["sessions"])
def create_session(
    campaign_id: int,
    request: Request,
    files: list[UploadFile] = File(..., description="One save per in-game year"),
    name: str | None = Form(None),
    played_on: date | None = Form(None),
    notes: str | None = Form(None),
) -> dict:
    store, ingestor = _store(request), _ingestor(request)
    session_id = store.create_session(campaign_id, name, played_on.isoformat() if played_on else None, notes)
    saves = [ingestor.add_upload(session_id, f.file, f.filename or "save.eu5") for f in files]
    return {"session_id": session_id, "saves": saves}


@router.get("/campaigns/{campaign_id}/sessions", tags=["sessions"])
def list_sessions(campaign_id: int, request: Request) -> list[dict]:
    return _store(request).list_sessions(campaign_id)


@router.get("/sessions/{session_id}", tags=["sessions"])
def get_session(session_id: int, request: Request) -> dict:
    return _store(request).get_session(session_id)


@router.post("/sessions/{session_id}/saves", status_code=202, tags=["sessions"])
def add_session_saves(session_id: int, request: Request, files: list[UploadFile] = File(...)) -> dict:
    store, ingestor = _store(request), _ingestor(request)
    store.get_session(session_id, with_saves=False)
    saves = [ingestor.add_upload(session_id, f.file, f.filename or "save.eu5") for f in files]
    return {"session_id": session_id, "saves": saves}


@router.delete("/sessions/{session_id}", status_code=204, tags=["sessions"])
def delete_session(session_id: int, request: Request):
    orphan_files = _store(request).delete_session(session_id)
    _ingestor(request).remove_files(orphan_files)


@router.get("/sessions/{session_id}/summary", tags=["sessions"])
def session_summary(session_id: int, request: Request) -> dict:
    return _store(request).session_summary(session_id)


# ---------------------------------------------------------------------- saves
@router.get("/saves/{save_id}", tags=["saves"])
def get_save(save_id: int, request: Request) -> dict:
    return _store(request).get_save(save_id)


@router.post("/saves/{save_id}/reprocess", status_code=202, tags=["saves"])
def reprocess_save(save_id: int, request: Request) -> dict:
    n = _store(request).mark_pending(save_id=save_id)
    _ingestor(request).notify()
    return {"queued": n}


# ---------------------------------------------------------------------- statistics
@router.get("/campaigns/{campaign_id}/series", tags=["stats"])
def series(
    campaign_id: int,
    request: Request,
    metric: str = Query(..., description="See /metrics"),
    tag: str | None = Query(None, description="Current or past tag of the country"),
    session: int | None = None,
) -> dict:
    if metric not in METRICS_BY_NAME:
        raise HTTPException(422, f"Unknown metric {metric!r}; see /metrics")
    points = _store(request).series(campaign_id, metric, tag=tag.upper() if tag else None, session_id=session)
    return {"metric": metric, "points": points}


@router.get("/campaigns/{campaign_id}/history", tags=["stats"])
def history(campaign_id: int, request: Request, metric: str = Query(..., description="See /metrics")) -> dict:
    if metric not in HISTORY_METRICS:
        raise HTTPException(422, f"Unknown history metric {metric!r}; one of {HISTORY_METRICS}")
    return {"metric": metric, **_store(request).history(campaign_id, metric)}
