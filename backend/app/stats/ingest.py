"""Storing uploaded saves and processing them in a background worker thread."""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import BinaryIO

from app.eu5.container import HEADER_LEN, SaveFormatError, parse_header
from app.eu5.tokens import TokenTable

from .db import Store
from .extract import extract

log = logging.getLogger("eu5stats.ingest")
CHUNK = 1 << 20


class Ingestor:
    def __init__(self, store: Store, uploads_dir: Path | str, tokens: TokenTable):
        self.store = store
        self.uploads = Path(uploads_dir)
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.tokens = tokens
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ uploads
    def path_for(self, sha256: str) -> Path:
        return self.uploads / f"{sha256}.eu5"

    def add_upload(self, session_id: int, fileobj: BinaryIO, file_name: str) -> dict:
        """Stream an uploaded file to disk (content-addressed) and register it in the session."""
        sha = hashlib.sha256()
        fd, tmp_name = tempfile.mkstemp(dir=self.uploads, suffix=".part")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                head = b""
                while chunk := fileobj.read(CHUNK):
                    if len(head) < HEADER_LEN:
                        head += chunk[: HEADER_LEN - len(head)]
                    sha.update(chunk)
                    out.write(chunk)
            digest = sha.hexdigest()
            try:
                parse_header(head)
            except SaveFormatError as e:
                tmp.unlink(missing_ok=True)
                return self.store.add_save(session_id, digest, file_name, status="error", error=str(e))

            result = self.store.add_save(session_id, digest, file_name)
            final = self.path_for(digest)
            if final.exists():
                tmp.unlink(missing_ok=True)
            else:
                tmp.replace(final)
            if result["status"] == "pending":
                self._wake.set()
            return result
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def remove_files(self, shas: list[str]) -> None:
        for s in shas:
            self.path_for(s).unlink(missing_ok=True)

    # ------------------------------------------------------------------ processing
    def process_save(self, save: dict) -> None:
        save_id = save["id"]
        try:
            data = self.path_for(save["sha256"]).read_bytes()
            stats = extract(data, self.tokens, self.store.tracked_countries(save["campaign_id"]))
            self.store.store_stats(save_id, stats)
            log.info("Processed save %s (%s): %d countries", save_id, stats.game_date, len(stats.countries))
        except Exception as e:  # noqa: BLE001 - any failure is recorded on the save
            log.exception("Failed to process save %s", save_id)
            self.store.mark_error(save_id, f"{type(e).__name__}: {e}")

    def process_pending(self) -> int:
        n = 0
        while not self._stop.is_set():
            save = self.store.claim_next_pending()
            if save is None:
                break
            self.process_save(save)
            n += 1
        return n

    def notify(self) -> None:
        self._wake.set()

    # ------------------------------------------------------------------ worker
    def start(self) -> None:
        self.store.reset_processing()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="eu5-ingest", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_pending()
            except Exception:  # noqa: BLE001 - keep the worker alive
                log.exception("Worker loop error")
            self._wake.wait(timeout=5)
            self._wake.clear()
