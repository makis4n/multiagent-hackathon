"""Streamlit page: the brief on the left, itinerary and bookings on the right. Only Lane A edits this file.

Three steps, kept in session state: brief -> questions -> plan. Bookings wait for a click on each option.
"""

from __future__ import annotations

import datetime as dt
import html
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

FONT_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=IBM+Plex+Mono:wght@400;500;600"
    "&family=Newsreader:ital,wght@0,400;0,500;0,600;1,400;1,500"
    "&display=swap"
)

# A field-notebook manifest: signals read like index cards, the itinerary reads like a ledger,
# bookings read like ticket stubs. Verified/draft/failed reuse the theme's semantic colours
# (config.toml) so status here always matches st.success/warning/error elsewhere on the page.
STYLE_BLOCK = f"""
<style>
@import url("{FONT_LINK}");

[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li {{
  line-height: 1.55;
}}

.hero {{ margin: 0 0 1rem 0; }}
.hero-title {{ margin: 0; }}
.hero-tag {{
  margin: 0.15rem 0 0 0;
  font-size: 0.85rem;
  color: color-mix(in srgb, var(--text-color, #3A2A1E) 65%, transparent);
  max-width: 46ch;
}}

.step-track {{ display: flex; align-items: center; margin: 0 0 1.5rem 0; }}
.step {{
  font-size: 0.72rem;
  padding: 0.25rem 0.7rem;
  border: 1px solid #CEAD79;
  border-radius: 0.3rem;
  opacity: 0.45;
}}
.step[data-state="active"] {{
  opacity: 1;
  font-weight: 600;
  color: #C1650B;
  border-color: #C1650B;
  background: color-mix(in srgb, #C1650B 12%, transparent);
}}
.step[data-state="done"] {{
  opacity: 0.85;
  color: #4A6430;
  border-color: #5E7C3A;
  background: color-mix(in srgb, #5E7C3A 10%, transparent);
}}
.step-connector {{ flex: 0 0 1.4rem; height: 1px; background: #CEAD79; margin: 0 0.1rem; }}

.trip-strip {{
  display: flex;
  flex-wrap: wrap;
  border: 1px dashed #CEAD79;
  border-radius: 0.6rem;
  background: color-mix(in srgb, #EDDCB6 60%, transparent);
  margin: 0.5rem 0 1.5rem 0;
  overflow: hidden;
}}
.trip-cell {{
  padding: 0.55rem 1rem;
  border-right: 1px dashed #CEAD79;
}}
.trip-cell:last-child {{ border-right: none; }}
.trip-cell-label {{ display: block; font-size: 0.65rem; opacity: 0.6; margin-bottom: 0.15rem; }}
.trip-cell-value {{ font-weight: 600; font-variant-numeric: tabular-nums; }}

.tool-row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 1.1rem 0; }}
.tool-tag {{
  font-size: 0.68rem;
  padding: 0.15rem 0.55rem;
  border: 1px solid #CEAD79;
  border-radius: 0.3rem;
  color: #3A2A1E;
  opacity: 0.55;
}}
.tool-tag[data-on="1"] {{
  opacity: 1;
  color: #4A6430;
  border-color: #5E7C3A;
  background: color-mix(in srgb, #5E7C3A 12%, transparent);
}}
.tool-tag[data-on="fail"] {{
  opacity: 1;
  color: #86321F;
  border-color: #9C3D28;
  background: color-mix(in srgb, #9C3D28 12%, transparent);
}}

.signal-card {{
  border-left: 3px solid #CEAD79;
  border-radius: 0 0.6rem 0.6rem 0;
  padding: 0.5rem 0.85rem 0.65rem 0.75rem;
  margin-bottom: 0.9rem;
}}
.signal-card[data-source="reddit"] {{
  border-left-color: #A67C3D;
  background: color-mix(in srgb, #A67C3D 9%, transparent);
}}
.signal-card[data-source="youtube"] {{
  border-left-color: #9C3D28;
  background: color-mix(in srgb, #9C3D28 8%, transparent);
}}
.signal-card[data-source="web"] {{
  border-left-color: #5E7C3A;
  background: color-mix(in srgb, #5E7C3A 8%, transparent);
}}
.signal-quote {{
  font-family: "Newsreader", serif;
  font-style: italic;
  font-size: 1.03rem;
  line-height: 1.45;
  margin: 0 0 0.3rem 0;
}}
.signal-title {{ font-size: 0.8rem; }}
.signal-meta {{
  display: flex;
  gap: 0.7rem;
  margin-top: 0.15rem;
  font-size: 0.72rem;
  opacity: 0.6;
}}
.signal-source {{ text-transform: lowercase; }}

.day-block {{ margin-bottom: 1.6rem; }}
.day-title {{
  font-family: "Newsreader", serif;
  font-weight: 600;
  font-size: 1.2rem;
  border-bottom: 1px solid #CEAD79;
  padding-bottom: 0.25rem;
  margin-bottom: 0.1rem;
}}
table.manifest {{ width: 100%; border-collapse: collapse; }}
table.manifest td {{
  vertical-align: top;
  padding: 0.55rem 0.5rem 0.55rem 0;
  border-bottom: 1px dashed #CEAD79;
}}
table.manifest tr:last-child td {{ border-bottom: none; }}
.stop-time {{
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  opacity: 0.7;
  font-size: 0.85rem;
  width: 6.5rem;
}}
.stop-cat {{ opacity: 0.55; font-size: 0.8rem; width: 5.5rem; }}
.stop-place {{ font-weight: 600; margin-right: 0.5rem; }}
.stop-status {{ font-size: 0.72rem; }}
.stop-status::before {{ content: "\\25A0"; font-size: 0.55rem; margin-right: 0.3rem; }}
.stop-status[data-status="verified"] {{ color: #4A6430; }}
.stop-status[data-status="draft"] {{ color: #8C6329; }}
.stop-status[data-status="failed"] {{ color: #86321F; }}
.stop-why {{
  font-family: "Newsreader", serif;
  font-style: italic;
  font-size: 0.92rem;
  opacity: 0.85;
  margin: 0.2rem 0 0 0;
}}

div[class*="st-key-ticket-"] {{
  border: 1px dashed #CEAD79;
  border-radius: 0.6rem;
  background: #EDDCB6;
  box-shadow: 0 4px 14px color-mix(in srgb, #C1650B 14%, transparent);
  padding: 0.7rem 0.9rem 0.5rem 0.9rem;
  margin-bottom: 0.7rem;
}}
.ticket-kind {{ font-size: 0.7rem; opacity: 0.55; }}
.ticket-title {{ display: block; font-weight: 600; }}
.ticket-price {{ display: block; font-variant-numeric: tabular-nums; opacity: 0.7; font-size: 0.85rem; }}
</style>
"""


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Trip agent", layout="wide")
    st.html(STYLE_BLOCK)
    if "tools" not in st.session_state:
        st.session_state["tools"] = build_tools()
    tools: Tools = st.session_state["tools"]
    with st.sidebar:
        brief_form(tools)
        state = current_state()
        if state is not None and state.report is None:
            questions_form(state, tools)
        if state is not None:
            signals_list(state)
    hero()
    state = current_state()
    step_indicator(state)
    if state is None or state.itinerary is None:
        st.info("Fill in the brief on the left, then press Plan trip.")
    elif state.report is None:
        draft_view(state)
    else:
        plan_view(state, tools)


def hero() -> None:
    st.markdown(
        '<div class="hero">'
        '<h1 class="hero-title">Trip agent</h1>'
        '<p class="hero-tag">Reddit and YouTube tips, checked against real hours and routes, '
        "booked only when you say so.</p>"
        "</div>",
        unsafe_allow_html=True,
    )


STEPS = ("Brief", "Questions", "Book")


def step_indicator(state: TripState | None) -> None:
    if state is None:
        current = 0
    elif state.report is None:
        current = 1
    else:
        current = 2
    parts = []
    for index, label in enumerate(STEPS):
        status = "done" if index < current else "active" if index == current else "pending"
        parts.append(f'<span class="step" data-state="{status}">{esc(label)}</span>')
        if index != len(STEPS) - 1:
            parts.append('<span class="step-connector"></span>')
    st.markdown(f'<div class="step-track">{"".join(parts)}</div>', unsafe_allow_html=True)


def departure_countdown(start_date: dt.date) -> str:
    days = (start_date - dt.date.today()).days
    if days > 1:
        return f"{days} days"
    if days == 1:
        return "tomorrow"
    if days == 0:
        return "today"
    return "underway"


def trip_strip(state: TripState) -> None:
    brief = state.brief
    cells = [
        ("Dates", f"{brief.start_date:%d %b}–{brief.end_date:%d %b}"),
        ("Travellers", str(brief.travellers)),
        ("Budget", brief.budget_band.value),
        ("Departs in", departure_countdown(brief.start_date)),
    ]
    body = "".join(
        f'<div class="trip-cell"><span class="trip-cell-label">{esc(label)}</span>'
        f'<span class="trip-cell-value">{esc(value)}</span></div>'
        for label, value in cells
    )
    st.markdown(f'<div class="trip-strip">{body}</div>', unsafe_allow_html=True)


def esc(value: object) -> str:
    return html.escape(str(value))


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
    tools_status()


def tools_status() -> None:
    chips = "".join(
        f'<span class="tool-tag" data-on="{"1" if on else "0"}">{esc(name.lower())}</span>'
        for name, on in active_flags().items()
    )
    if inject_booking_failure():
        chips += '<span class="tool-tag" data-on="fail">failure injected</span>'
    st.markdown(f'<div class="tool-row">{chips}</div>', unsafe_allow_html=True)


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
        when = "" if signal.posted_at is None else f"{signal.posted_at:%d %b %Y}"
        st.markdown(
            f'<div class="signal-card" data-source="{esc(signal.source.value)}">'
            f'<p class="signal-quote">“{esc(signal.excerpt)}”</p>'
            f'<a class="signal-title" href="{esc(signal.url)}" target="_blank" rel="noopener">{esc(signal.title)}</a>'
            f'<div class="signal-meta"><span class="signal-source">{esc(signal.source.value)}</span>'
            f"<span>{esc(when)}</span></div>"
            "</div>",
            unsafe_allow_html=True,
        )


def itinerary_view(state: TripState) -> None:
    if state.itinerary is None:
        return
    for day in state.itinerary.days:
        rows = []
        for stop in day.stops:
            reason = f' title="{esc(stop.failure_reason)}"' if stop.failure_reason else ""
            status = esc(stop.status.value)
            rows.append(
                "<tr>"
                f'<td class="stop-time">{stop.start:%H:%M}–{stop.end:%H:%M}</td>'
                f'<td class="stop-cat">{esc(stop.category)}</td>'
                "<td>"
                f'<span class="stop-place">{esc(stop.place_name)}</span>'
                f'<span class="stop-status" data-status="{status}"{reason}>{status}</span>'
                f'<p class="stop-why">{esc(stop.why)}</p>'
                "</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="day-block">'
            f'<div class="day-title">{day.date:%A %d %B}</div>'
            f'<table class="manifest"><tbody>{"".join(rows)}</tbody></table>'
            "</div>",
            unsafe_allow_html=True,
        )


def draft_view(state: TripState) -> None:
    assert state.itinerary is not None
    st.subheader(f"{state.brief.destination}: draft")
    st.caption("Not checked yet. Answer the questions on the left to verify and finish it.")
    trip_strip(state)
    itinerary_view(state)


def plan_view(state: TripState, tools: Tools) -> None:
    assert state.itinerary is not None and state.report is not None
    st.subheader(state.brief.destination)
    trip_strip(state)
    metric, swaps = st.columns([1, 3])
    metric.metric("Stops verified", f"{state.report.pass_rate():.0%}")
    for swap in state.replacements:
        took = f"swapped for {swap.new.place_name}" if swap.new else "removed"
        swaps.warning(f"{swap.old.place_name}: {swap.reason}; {took}.")
    itinerary_view(state)
    st.subheader("Book")
    for option in state.options:
        with st.container(key=f"ticket-{option.provider_ref}"):
            kind_col, info_col, action_col = st.columns([0.8, 3.2, 1])
            kind_col.markdown(f'<span class="ticket-kind">{esc(option.kind.value)}</span>', unsafe_allow_html=True)
            info_col.markdown(
                f'<span class="ticket-title">{esc(option.title)}</span>'
                f'<span class="ticket-price">{option.price_minor / 100:,.0f} {esc(option.currency)}</span>',
                unsafe_allow_html=True,
            )
            if action_col.button("Book", key=option.provider_ref, width="stretch"):
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
