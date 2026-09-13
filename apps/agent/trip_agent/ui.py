"""Streamlit page: the brief on the left, itinerary and bookings on the right. Only Lane A edits this file.

Three steps, kept in session state: brief -> questions -> plan. Bookings wait for a click on each option.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from trip_agent.log import CallLog
from trip_agent.loop import (
    Tools,
    order,
    stage_calendar,
    stage_draft,
    stage_refine,
    stage_research,
    stage_search,
    stage_verify,
)
from trip_agent.registry import active_flags, build_tools, inject_booking_failure
from trip_core.models import BudgetBand, TripBrief, TripState

STYLES = ["food", "art", "museums", "nightlife", "nature", "family", "shopping", "neighbourhood walks"]


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Trip agent", layout="wide")
    if "tools" not in st.session_state:
        st.session_state["tools"] = build_tools()
    tools: Tools = st.session_state["tools"]
    left, right = st.columns([1, 1.6])
    with left:
        brief_form(tools)
        state = current_state()
        if state is not None and state.report is None:
            questions_form(state, tools)
        if state is not None:
            signals_list(state)
    with right:
        state = current_state()
        if state is None or state.itinerary is None:
            st.info("Fill in the brief and press Plan trip.")
        elif state.report is None:
            draft_view(state)
        else:
            plan_view(state, tools)


def current_state() -> TripState | None:
    state = st.session_state.get("state")
    return state if isinstance(state, TripState) else None


def log_for(state: TripState) -> CallLog:
    return CallLog(Path("logs/calls.jsonl"), state.brief.id)


def brief_form(tools: Tools) -> None:
    st.subheader("Where to?")
    with st.form("brief"):
        destination = st.text_input("Destination", "Tokyo")
        origin = st.text_input("Flying from (airport code)", "ARN")
        destination_code = st.text_input(
            "Destination airport code", "TYO", help="IATA code Duffel searches, e.g. TYO, LIS, NYC"
        )
        start = st.date_input("Start", dt.date(2026, 11, 12))
        end = st.date_input("End", dt.date(2026, 11, 16))
        travellers = st.number_input("Travellers", min_value=1, max_value=8, value=2)
        budget = st.selectbox("Budget", [band.value for band in BudgetBand], index=1)
        styles = st.multiselect("Styles", STYLES, ["food", "art"])
        submitted = st.form_submit_button("Plan trip")
    if submitted and isinstance(start, dt.date) and isinstance(end, dt.date):
        brief = TripBrief(
            id=f"ui-{re.sub(r'[^a-z0-9]+', '-', destination.lower())}-{start:%Y%m%d}",
            destination=destination,
            origin=origin,
            destination_code=destination_code.strip() or None,
            start_date=start,
            end_date=end,
            travellers=int(travellers),
            budget_band=BudgetBand(budget),
            styles=styles,
        )
        state = TripState(brief=brief)
        with st.status("Researching and drafting", expanded=False) as status:
            state = stage_draft(stage_research(state, tools, log_for(state)), tools, log_for(state))
            status.update(label="Draft ready. A few questions before it is checked.", state="complete")
        st.session_state["state"] = state
        st.rerun()
    real = [name.lower() for name, on in active_flags().items() if on]
    injected = " · booking failure injected" if inject_booking_failure() else ""
    st.caption("Real tools: " + (", ".join(real) or "none, all fakes") + injected)


def questions_form(state: TripState, tools: Tools) -> None:
    st.subheader("A few questions")
    with st.form("questions"):
        answers = {
            question: st.text_input(
                question,
                value="skip: Shibuya Sky"
                if question == "Anything to skip?" and state.brief.destination == "Tokyo"
                else "",
                help="Answers shaped skip: <place> remove that stop",
            )
            for question in state.questions
        }
        go = st.form_submit_button("Check and finish the plan")
    if go:
        with st.status("Refining and verifying every stop", expanded=False) as status:
            state = stage_verify(stage_refine(state, tools, log_for(state), answers), tools, log_for(state))
            state = stage_calendar(stage_search(state, tools, log_for(state)), tools, log_for(state))
            status.update(label="Verified. Bookings wait for your click.", state="complete")
        st.session_state["state"] = state
        st.rerun()


def signals_list(state: TripState) -> None:
    st.subheader("What people are saying")
    for signal in state.signals[:12]:
        when = "" if signal.posted_at is None else f" · {signal.posted_at:%d %b %Y}"
        st.markdown(f"- [{signal.title}]({signal.url}) · {signal.source.value}{when}")


def itinerary_tables(state: TripState) -> None:
    if state.itinerary is None:
        return
    for day in state.itinerary.days:
        st.markdown(f"**{day.date:%A %d %B}**")
        st.table(
            [
                {
                    "time": f"{stop.start:%H:%M}-{stop.end:%H:%M}",
                    "place": stop.place_name,
                    "what": stop.category,
                    "status": stop.status.value,
                    "why": stop.why,
                }
                for stop in day.stops
            ]
        )


def draft_view(state: TripState) -> None:
    assert state.itinerary is not None
    st.subheader(f"{state.brief.destination}, {len(state.itinerary.days)} days: draft")
    st.caption("Nothing here is checked yet. Answer the questions on the left to verify and finish it.")
    itinerary_tables(state)


def plan_view(state: TripState, tools: Tools) -> None:
    assert state.itinerary is not None and state.report is not None
    st.subheader(f"{state.brief.destination}, {len(state.itinerary.days)} days")
    metric, swaps = st.columns([1, 3])
    metric.metric("Stops verified", f"{state.report.pass_rate():.0%}")
    for swap in state.replacements:
        took = f"swapped for {swap.new.place_name}" if swap.new else "removed"
        swaps.warning(f"{swap.old.place_name}: {swap.reason}; {took}.")
    itinerary_tables(state)
    st.subheader("Book")
    for option in state.options:
        text, action = st.columns([4, 1])
        text.write(f"{option.title} · {option.price_minor / 100:.0f} {option.currency}")
        if action.button("Book", key=option.provider_ref, width="stretch"):
            placed = order(state, tools, log_for(state), option, dt.datetime.now(dt.UTC))
            if placed.idempotency_key not in {existing.idempotency_key for existing in state.orders}:
                state.orders.append(placed)
            st.session_state["state"] = state
    for placed in state.orders:
        st.success(f"{placed.option.kind.value}: {placed.provider_order_id} ({placed.status.value})")
    if state.calendar_url:
        st.link_button("Open calendar", state.calendar_url)


if __name__ == "__main__":
    main()
