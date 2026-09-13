"""Run every brief in evals/trips through the loop and write evals/results/<sha>.md.

The flags in .env decide whether real tools or fakes run; the table says which. Usage: make evals
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

import httpx
from dotenv import load_dotenv

from trip_agent.log import CallLog
from trip_agent.loop import run
from trip_agent.registry import active_flags, build_tools
from trip_core.models import MAX_TRANSIT_MINUTES, BookingKind, CheckKind, TripBrief, TripState

ROOT = Path(__file__).resolve().parent
TRIPS = ROOT / "trips"
RESULTS = ROOT / "results"
URL_SAMPLE = 10

Verdict = tuple[bool, str]


def check_signals(state: TripState) -> Verdict:
    places = {place for signal in state.signals for place in signal.places_mentioned}
    ok = len(state.signals) >= 15 and len(places) >= 10
    detail = f"{len(state.signals)} signals, {len(places)} places"
    if active_flags()["RESEARCH"]:
        dead = dead_urls([signal.url for signal in state.signals[:URL_SAMPLE]])
        ok = ok and not dead
        detail += f", {len(dead)} dead of {min(len(state.signals), URL_SAMPLE)} URLs checked"
    return ok, detail


def dead_urls(urls: list[str]) -> list[str]:
    """URLs that do not answer 2xx or 3xx within 5 seconds. Only meaningful for real research."""
    dead: list[str] = []
    with httpx.Client(timeout=5.0, follow_redirects=True, headers={"User-Agent": "trip-agent-evals/0.1"}) as client:
        for url in urls:
            try:
                if client.get(url).status_code >= 400:
                    dead.append(url)
            except httpx.HTTPError:
                dead.append(url)
    return dead


def check_resolved(state: TripState) -> Verdict:
    stops = state.itinerary.stops() if state.itinerary else []
    unresolved = [stop.place_name for stop in stops if stop.place_id is None]
    return bool(stops) and not unresolved, f"{len(stops) - len(unresolved)}/{len(stops)} resolved"


def check_verified(state: TripState) -> Verdict:
    if state.report is None:
        return False, "no report"
    return state.report.pass_rate() >= 0.9, f"{state.report.pass_rate():.0%} of stops pass"


def check_transit(state: TripState) -> Verdict:
    if state.report is None:
        return False, "no report"
    legs = [check for check in state.report.checks if check.check == CheckKind.reachable]
    minutes = [int(match.group(1)) for check in legs if (match := re.match(r"(\d+) min", check.detail))]
    return all(check.ok for check in legs), f"worst leg {max(minutes, default=0)} min of {MAX_TRANSIT_MINUTES}"


def check_bookable(state: TripState) -> Verdict:
    kinds = {option.kind for option in state.options}
    return {BookingKind.flight, BookingKind.stay} <= kinds, ", ".join(sorted(kind.value for kind in kinds)) or "none"


def check_gated(state: TripState) -> Verdict:
    keys = {order.idempotency_key for order in state.orders}
    ok = len(keys) == len(state.orders) and all(order.confirmed_by_user_at is not None for order in state.orders)
    return ok, f"{len(state.orders)} orders, {len(keys)} keys"


CHECKS: dict[str, Callable[[TripState], Verdict]] = {
    "signals": check_signals,
    "resolved": check_resolved,
    "verified": check_verified,
    "transit": check_transit,
    "bookable": check_bookable,
    "gated": check_gated,
}
COLUMNS = [*CHECKS, "loop"]


def head_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT
        )
    except (OSError, subprocess.CalledProcessError):
        return "local"
    return completed.stdout.strip()


def main() -> int:
    load_dotenv()
    tools = build_tools()
    sha = head_sha()
    log_path = ROOT.parent / "logs" / f"evals-{sha}.jsonl"
    briefs = sorted(TRIPS.glob("*.json"))
    totals = dict.fromkeys(COLUMNS, 0)
    rows: list[str] = []
    for path in briefs:
        brief = TripBrief.model_validate_json(path.read_text())
        log = CallLog(log_path, brief.id)
        failure: str | None = None
        state: TripState | None = None
        try:
            state = run(brief, tools, log, confirm=lambda option: dt.datetime.now(dt.UTC))
        except Exception:
            failure = traceback.format_exc().strip().splitlines()[-1]
        cells: list[str] = []
        for name, check in CHECKS.items():
            if state is None:
                cells.append("✗ not run")
                continue
            ok, detail = check(state)
            totals[name] += int(ok)
            cells.append(f"{'✓' if ok else '✗'} {detail}")
        loop_ok = failure is None and len(log.entries()) >= 8
        totals["loop"] += int(loop_ok)
        cells.append("✓" if loop_ok else f"✗ {failure or 'too few calls logged'}")
        rows.append(f"| {path.stem} | " + " | ".join(cells) + " |")
    flags = ", ".join(name.lower() for name, on in active_flags().items() if on) or "none (all fakes)"
    lines = [
        f"# Eval results @ {sha}",
        "",
        f"Run {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. Real tools: {flags}. "
        f"Call log: `{log_path.relative_to(ROOT.parent)}`.",
        "",
        "| trip | " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * (len(COLUMNS) + 1),
        *rows,
        "| **pass** | " + " | ".join(f"{totals[name]}/{len(briefs)}" for name in COLUMNS) + " |",
        "",
    ]
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{sha}.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
