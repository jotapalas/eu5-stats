from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import orjson
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from app.eu5.container import SaveFormatError
from app.eu5.decoder import SECTIONS, decode_save
from app.eu5.lexer import TokenError
from app.eu5.tokens import TokenTable
from app.stats.api import router as stats_router
from app.stats.db import Conflict, NotFound, Store
from app.stats.ingest import Ingestor

DEFAULT_DATA_DIR = Path(os.environ.get("EU5_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(data_dir: Path | str = DEFAULT_DATA_DIR, *, start_worker: bool = True) -> FastAPI:
    data_dir = Path(data_dir)
    tokens = TokenTable.load()
    store = Store(data_dir / "eu5stats.db")
    ingestor = Ingestor(store, data_dir / "uploads", tokens)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_worker:
            ingestor.start()
        try:
            yield
        finally:
            if start_worker:
                ingestor.stop()

    app = FastAPI(title="EU5 save stats", lifespan=lifespan)
    app.state.store = store
    app.state.ingestor = ingestor
    app.include_router(stats_router)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict(_: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "known_tokens": len(tokens.names)}

    @app.post("/decode", tags=["decoder"])
    def decode(
        file: UploadFile,
        sections: str = Query(",".join(SECTIONS), description="Comma-separated: header,metadata,gamestate"),
        dates: bool = Query(True, description="Render i32 values in the date range as Y.M.D strings"),
        strict: bool = Query(True, description="Fail on unknown value tokens instead of returning a partial result"),
        select: str | None = Query(None, description="Comma-separated top-level gamestate keys to keep, e.g. countries,played_country"),
    ) -> Response:
        # Sync endpoint: FastAPI runs it in a threadpool, so the CPU-bound decode doesn't block the loop.
        wanted = tuple(s.strip() for s in sections.split(",") if s.strip())
        selected = tuple(s.strip() for s in select.split(",") if s.strip()) if select else None
        data = file.file.read()
        try:
            result = decode_save(data, sections=wanted, tokens=tokens, dates=dates, strict=strict, select=selected)
        except (SaveFormatError, TokenError, ValueError, IndexError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return Response(orjson.dumps(result), media_type="application/json")

    return app


app = create_app()
