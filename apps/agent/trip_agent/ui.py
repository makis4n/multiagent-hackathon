"""Streamlit page: the brief on the left, itinerary and bookings on the right. Only Lane A edits this file."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from trip_agent.log import CallLog
from trip_agent.loop import Tools, run
from trip_agent.registry import active_flags, build_tools
from trip_core.models import BudgetBand, TripBrief, TripState, idempotency_key

STYLES = ["food", "art", "museums", "nightlife", "nature", "family", "shopping", "neighbourhood walks"]


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Trip agent", layout="wide")
    if "tools" not in st.session_state:
        st.session_state["tools"] = build_tools()
    tools: Tools = st.session_state["tools"]
    left, right = st.columns([1, 1.6])

    with left:
        st.subheader("Where to?")
        with st.form("brief"):
            destination = st.text_input("Destination", "Tokyo")
            origin = st.text_input("Flying from", "ARN")
            start = st.date_input("Start", dt.date(2026, 11, 12))
            end = st.date_input("End", dt.date(2026, 11, 16))
            travellers = st.number_input("Travellers", min_value=1, max_value=8, value=2)
            budget = st.selectbox("Budget", [band.value for band in BudgetBand], index=1)
            styles = st.multiselect("Styles", STYLES, ["food", "art"])
            skip = st.text_input("Anything to skip?", placeholder="skip: Shibuya Sky")
            submitted = st.form_submit_button("Plan trip")
        if submitted and isinstance(start, dt.date) and isinstance(end, dt.date):
            brief = TripBrief(
                id=f"ui-{re.sub(r'[^a-z0-9]+', '-', destination.lower())}-{start:%Y%m%d}",
                destination=destination,
                origin=origin,
                start_date=start,
                end_date=end,
                travellers=int(travellers),
                budget_band=BudgetBand(budget),
                styles=styles,
                answers={"Anything to skip?": skip} if skip else {},
            )
            log = CallLog(Path("logs/calls.jsonl"), brief.id)
            with st.status("Planning", expanded=True) as status:
                state = run(brief, tools, log, confirm=lambda option: None)
                status.update(label="Planned. Bookings wait for your confirmation.", state="complete")
            st.session_state["state"] = state
        real = [name.lower() for name, on in active_flags().items() if on]
        st.caption("Real tools: " + (", ".join(real) or "none, all fakes"))
        state = st.session_state.get("state")
        if isinstance(state, TripState):
            st.subheader("What people are saying")
            for signal in state.signals[:12]:
                when = "" if signal.posted_at is None else f" · {signal.posted_at:%d %b %Y}"
                st.markdown(f"- [{signal.title}]({signal.url}) · {signal.source}{when}")

    with right:
        state = st.session_state.get("state")
        if not isinstance(state, TripState) or state.itinerary is None:
            st.info("Fill in the brief and press Plan trip.")
            return
        st.subheader(f"{state.brief.destination}, {len(state.itinerary.days)} days")
        if state.report is not None:
            st.metric("Stops verified", f"{state.report.pass_rate():.0%}")
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
        st.subheader("Book")
        for option in state.options:
            text, action = st.columns([3, 1])
            text.write(f"{option.title} · {option.price_minor / 100:.0f} {option.currency}")
            if action.button("Confirm and book", key=option.provider_ref):
                key = idempotency_key(state.brief.id, option)
                order = tools.booking.order(option, key, dt.datetime.now(dt.UTC))
                if order.idempotency_key not in {existing.idempotency_key for existing in state.orders}:
                    state.orders.append(order)
                st.session_state["state"] = state
        for order in state.orders:
            st.success(f"{order.option.kind}: {order.provider_order_id} ({order.status.value})")
        if state.calendar_url:
            st.link_button("Open calendar", state.calendar_url)


if __name__ == "__main__":
    main()
