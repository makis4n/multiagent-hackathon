"""uv run trip --fixture tokyo --auto-confirm    or    uv run trip --brief evals/trips/lisbon.json"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from dotenv import load_dotenv

from trip_agent.log import CallLog
from trip_agent.loop import run
from trip_agent.registry import active_flags, build_tools
from trip_core.models import BookingOption, TripBrief, TripState, load_fixture


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="trip", description="Run one trip through the loop.")
    parser.add_argument("--fixture", help="fixture name under packages/core/trip_core/fixtures, e.g. tokyo")
    parser.add_argument("--brief", type=Path, help="path to a TripBrief JSON, e.g. evals/trips/lisbon.json")
    parser.add_argument("--auto-confirm", action="store_true", help="approve every booking without asking")
    parser.add_argument("--log", type=Path, default=Path("logs/calls.jsonl"), help="JSONL call log")
    parser.add_argument("--json", action="store_true", help="print the full TripState as JSON")
    args = parser.parse_args(argv)

    brief = load_brief(args.fixture, args.brief)
    log = CallLog(args.log, brief.id)
    interactive = sys.stdin.isatty() and not args.auto_confirm
    state = run(
        brief,
        build_tools(),
        log,
        confirm=auto_confirm if args.auto_confirm else prompt_confirm,
        ask=prompt_ask if interactive else None,
    )
    if args.json:
        print(state.model_dump_json(indent=2))
    else:
        print(summary(state, log))
    return 0


def load_brief(fixture: str | None, path: Path | None) -> TripBrief:
    if path is not None:
        return TripBrief.model_validate_json(path.read_text())
    return load_fixture(fixture or "tokyo").brief


def auto_confirm(option: BookingOption) -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def prompt_confirm(option: BookingOption) -> dt.datetime | None:
    if not sys.stdin.isatty():
        return None
    reply = input(f"Book {option.title} for {option.price_minor / 100:.0f} {option.currency}? [y/N] ")
    return dt.datetime.now(dt.UTC) if reply.strip().lower() in {"y", "yes"} else None


def prompt_ask(question: str) -> str | None:
    reply = input(f"{question} ")
    return reply.strip() or None


def summary(state: TripState, log: CallLog) -> str:
    brief = state.brief
    lines = [
        f"{brief.destination} from {brief.origin}, {brief.start_date} to {brief.end_date}, {brief.travellers} pax",
        f"signals: {len(state.signals)} from {', '.join(sorted({signal.source.value for signal in state.signals}))}",
    ]
    if state.itinerary is not None:
        stops = state.itinerary.stops()
        lines.append(f"itinerary v{state.itinerary.version}: {len(state.itinerary.days)} days, {len(stops)} stops")
        for day in state.itinerary.days:
            for stop in day.stops:
                flag = "" if stop.failure_reason is None else f"  <- {stop.failure_reason}"
                lines.append(f"  {day.date} {stop.start:%H:%M} {stop.place_name} [{stop.status}]{flag}")
    if state.report is not None:
        lines.append(
            f"verification: {'passed' if state.report.passed else 'FAILED'}, {state.report.pass_rate():.0%} of stops"
        )
    for order in state.orders:
        total = order.receipt.get("total_minor", order.option.price_minor) / 100
        lines.append(f"order {order.option.kind}: {order.provider_order_id} {total:.0f} {order.option.currency}")
    for error in state.errors:
        lines.append(f"note: {error}")
    lines.append(f"calendar: {state.calendar_url}")
    real = [name.lower() for name, on in active_flags().items() if on]
    lines.append(f"real tools: {', '.join(real) or 'none (all fakes)'}; {len(log.entries())} calls in {log.path}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
