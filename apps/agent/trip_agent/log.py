"""One JSONL line per tool call. The evals and the reliability brief are built from this file."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trip_core.models import RetryableError


class CallLog:
    def __init__(self, path: Path, trip_id: str) -> None:
        self.path = path
        self.trip_id = trip_id
        path.parent.mkdir(parents=True, exist_ok=True)

    def call[T](self, tool: str, fn: Callable[..., T], *args: Any, retries: int = 0, **kwargs: Any) -> T:
        """Run one tool call, log it, retry a RetryableError up to `retries` times. Everything else propagates."""
        input_hash = hashlib.sha256(repr((args, kwargs)).encode()).hexdigest()[:12]
        attempt = 0
        while True:
            attempt += 1
            started = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except RetryableError as error:
                self._write(tool, input_hash, attempt, started, ok=False, error=error)
                if attempt > retries:
                    raise
                continue
            except Exception as error:
                self._write(tool, input_hash, attempt, started, ok=False, error=error)
                raise
            self._write(tool, input_hash, attempt, started, ok=True, error=None)
            return result

    def _write(
        self, tool: str, input_hash: str, attempt: int, started: float, *, ok: bool, error: BaseException | None
    ) -> None:
        record: dict[str, Any] = {
            "event": "tool_call",
            "at": dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds"),
            "trip_id": self.trip_id,
            "tool": tool,
            "input_hash": input_hash,
            "attempt": attempt,
            "ms": round((time.perf_counter() - started) * 1000, 1),
            "ok": ok,
        }
        if error is not None:
            record["error"] = "".join(traceback.format_exception(error)).strip()[-2000:]
        with self.path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        return [record for record in records if record.get("trip_id") == self.trip_id]
