"""Record once, replay forever. Tests stay offline; CI never touches the network.

    data = cassette(Path(__file__).parent / "cassettes" / "reddit_tokyo.json", lambda: client.search(...).to_dict())

With RECORD=1 in the environment the fetch runs and its JSON-able result is written to the path. Without it the
file is replayed, and a missing file fails with the command that records it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


def cassette(path: Path, fetch: Callable[[], Any]) -> Any:
    if os.environ.get("RECORD") == "1":
        data = fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")
        return data
    if not path.exists():
        raise FileNotFoundError(
            f"no cassette at {path}; record it once with: RECORD=1 uv run pytest {path.parent.parent}"
        )
    return json.loads(path.read_text())
