"""Streamlit page: the brief on the left, itinerary and bookings on the right. Only Lane A edits this file.

Three steps, kept in session state: brief -> questions -> plan. Bookings wait for a click on each option.
While a stage runs the page shows a game-style loading bar (an iframe, so it animates while Python is busy).
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import string
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from streamlit.delta_generator import DeltaGenerator

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
from trip_agent.registry import build_tools
from trip_core.models import BudgetBand, Signal, TripBrief, TripState

STYLES = {
    "food": "🍜",
    "art": "🎨",
    "museums": "🏛️",
    "nightlife": "🌃",
    "nature": "🌿",
    "family": "🧸",
    "shopping": "🛍️",
    "neighbourhood walks": "🚶",
}
BUDGET_MIN, BUDGET_MAX = 30, 600
BUDGET_LOW_BELOW, BUDGET_HIGH_FROM = 100, 250
BUDGET_QUESTION = "Budget per person per day"
TITLE_CHARS = 58
SOURCE_LABEL = {"youtube": "YT", "reddit": "RD", "web": "WEB"}
DESTINATIONS = [
    "Amsterdam (AMS)",
    "Bali (DPS)",
    "Bangkok (BKK)",
    "Barcelona (BCN)",
    "Berlin (BER)",
    "Copenhagen (CPH)",
    "Dubai (DXB)",
    "Hong Kong (HKG)",
    "Istanbul (IST)",
    "Kyoto (OSA)",
    "Lisbon (LIS)",
    "London (LON)",
    "Los Angeles (LAX)",
    "Mexico City (MEX)",
    "New York (NYC)",
    "Paris (PAR)",
    "Prague (PRG)",
    "Rome (ROM)",
    "Seoul (SEL)",
    "Singapore (SIN)",
    "Sydney (SYD)",
    "Taipei (TPE)",
    "Tokyo (TYO)",
    "Vienna (VIE)",
]
ORIGINS = [
    "Amsterdam Schiphol (AMS)",
    "Bangkok Suvarnabhumi (BKK)",
    "Copenhagen (CPH)",
    "Dubai (DXB)",
    "Frankfurt (FRA)",
    "Gothenburg Landvetter (GOT)",
    "Helsinki Vantaa (HEL)",
    "Hong Kong (HKG)",
    "London Heathrow (LHR)",
    "Los Angeles (LAX)",
    "New York JFK (JFK)",
    "Oslo Gardermoen (OSL)",
    "Paris Charles de Gaulle (CDG)",
    "San Francisco (SFO)",
    "Seoul Incheon (ICN)",
    "Singapore Changi (SIN)",
    "Stockholm Arlanda (ARN)",
    "Sydney (SYD)",
    "Tokyo Haneda (HND)",
    "Tokyo Narita (NRT)",
]

FONT_LINK = (
    "https://fonts.googleapis.com/css2?"
    "family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800"
    "&family=Manrope:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500"
    "&display=swap"
)

STYLE_BLOCK = f"""
<style>
@import url("{FONT_LINK}");

:root {{
  --ink: #14171C; --muted: #5B6470; --line: #E1E5EB; --panel: #F3F5F8;
  --accent: #0B5FD9; --ok: #1B8A5A; --warn: #B7791F; --bad: #D23F31;
}}
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li {{ line-height: 1.55; }}
h1, h2, h3 {{ font-family: "Bricolage Grotesque", sans-serif; letter-spacing: -0.01em; }}

.hero {{ margin: 0.2rem 0 1.2rem 0; }}
.hero-kicker {{
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent);
  margin: 0 0 0.35rem 0;
}}
.hero-title {{
  font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: 2.6rem; line-height: 1.05; margin: 0;
}}
.hero-tag {{ margin: 0.5rem 0 0 0; color: var(--muted); max-width: 52ch; font-size: 1rem; }}

.banner {{
  position: relative; height: 15rem; border-radius: 1rem; overflow: hidden; margin: 0 0 1rem 0;
  background: var(--panel);
}}
.banner img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.banner-text {{
  position: absolute; left: 0; right: 0; bottom: 0; padding: 1.2rem 1.4rem;
  background: linear-gradient(to top, rgba(10, 14, 20, 0.82), rgba(10, 14, 20, 0));
  color: #fff;
}}
.banner-title {{
  font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: 2.4rem; line-height: 1; margin: 0;
}}
.banner-sub {{ margin: 0.3rem 0 0 0; font-size: 0.95rem; opacity: 0.9; }}

.step-track {{ display: flex; align-items: center; gap: 0.35rem; margin: 0 0 1.2rem 0; }}
.step {{
  font-size: 0.72rem; font-weight: 600; padding: 0.28rem 0.75rem; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted);
}}
.step[data-state="active"] {{ color: #fff; background: var(--ink); border-color: var(--ink); }}
.step[data-state="done"] {{
  color: var(--ok); border-color: color-mix(in srgb, var(--ok) 45%, transparent); background: #E3F5EC;
}}
.step-connector {{ flex: 0 0 1.2rem; height: 1px; background: var(--line); }}

.trip-strip {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0 0 1.4rem 0; }}
.trip-cell {{ padding: 0.5rem 0.9rem; border: 1px solid var(--line); border-radius: 0.7rem; min-width: 7rem; }}
.trip-cell-label {{
  display: block; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted);
}}
.trip-cell-value {{ font-weight: 700; font-variant-numeric: tabular-nums; }}

.src-list {{ display: flex; flex-direction: column; gap: 0.15rem; }}
.src {{
  display: grid; grid-template-columns: 2.4rem 1fr auto; gap: 0.5rem; align-items: baseline;
  padding: 0.35rem 0.4rem; border-radius: 0.5rem; text-decoration: none; color: var(--ink); font-size: 0.82rem;
}}
.src:hover {{ background: var(--panel); }}
.src-badge {{
  font-family: "JetBrains Mono", monospace; font-size: 0.62rem; font-weight: 700; text-align: center;
  padding: 0.12rem 0; border-radius: 0.3rem; color: #fff; background: var(--muted);
}}
.src-badge[data-source="youtube"] {{ background: var(--bad); }}
.src-badge[data-source="reddit"] {{ background: #E8651B; }}
.src-badge[data-source="web"] {{ background: var(--accent); }}
.src-title {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.src-date {{ font-size: 0.7rem; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.src-count {{ font-size: 0.78rem; color: var(--muted); margin: 0 0 0.4rem 0.4rem; }}

.day-block {{ margin-bottom: 1.5rem; }}
.day-title {{
  font-family: "Bricolage Grotesque", sans-serif; font-weight: 700; font-size: 1.25rem;
  display: flex; align-items: baseline; gap: 0.6rem; margin-bottom: 0.4rem;
}}
.day-title small {{ font-family: "Manrope", sans-serif; font-weight: 600; font-size: 0.78rem; color: var(--muted); }}
table.manifest {{ width: 100%; border-collapse: collapse; }}
table.manifest td {{ vertical-align: top; padding: 0.55rem 0.6rem 0.55rem 0; border-bottom: 1px solid var(--line); }}
table.manifest tr:last-child td {{ border-bottom: none; }}
.stop-photo {{ width: 6.8rem; }}
.stop-photo img, .stop-photo span {{
  width: 6.4rem; height: 4.6rem; border-radius: 0.6rem; display: block; object-fit: cover; background: var(--panel);
}}
.stop-time {{
  font-family: "JetBrains Mono", monospace; font-size: 0.78rem; color: var(--muted); white-space: nowrap;
  width: 6.6rem; padding-top: 0.7rem;
}}
.stop-place {{ font-weight: 700; font-size: 1rem; margin-right: 0.45rem; }}
.stop-cat {{
  font-size: 0.64rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted);
  border: 1px solid var(--line); border-radius: 999px; padding: 0.1rem 0.5rem; margin-right: 0.4rem;
  vertical-align: middle;
}}
.stop-status {{
  font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; border-radius: 999px;
  padding: 0.12rem 0.5rem; vertical-align: middle;
}}
.stop-status[data-status="verified"] {{ color: var(--ok); background: #E3F5EC; }}
.stop-status[data-status="draft"] {{ color: var(--warn); background: #FBF0DA; }}
.stop-status[data-status="failed"] {{ color: var(--bad); background: #FBE5E2; }}
.stop-why {{ color: var(--muted); font-size: 0.86rem; margin: 0.25rem 0 0 0; }}

.stat {{ border: 1px solid var(--line); border-radius: 0.9rem; padding: 0.8rem 1rem; }}
.stat-label {{
  display: block; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted);
}}
.stat-value {{
  font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: 2.2rem; line-height: 1.1;
  color: var(--ok);
}}
.swap-list {{ display: flex; flex-direction: column; gap: 0.35rem; }}
.swap {{
  display: grid; grid-template-columns: auto 1fr; gap: 0.6rem; font-size: 0.86rem; padding: 0.45rem 0.7rem;
  border-radius: 0.6rem; background: var(--panel);
}}
.swap-old {{ font-weight: 700; color: var(--bad); text-decoration: line-through; white-space: nowrap; }}
.swap-new b {{ color: var(--ok); }}
.swap-why {{ color: var(--muted); }}

div[class*="st-key-ticket-"] {{
  border: 1px solid var(--line); border-radius: 0.9rem; padding: 0.7rem 1rem 0.5rem 1rem; margin-bottom: 0.6rem;
}}
.ticket-kind {{
  font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted);
}}
.ticket-title {{ display: block; font-weight: 700; }}
.ticket-price {{
  display: block; font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: 1.25rem;
  font-variant-numeric: tabular-nums;
}}
.ticket-sub {{ display: block; font-size: 0.78rem; color: var(--muted); }}
</style>"""

# Loading bar in the style of a game's world-generation screen: a chunky segmented bar filling in steps, a
# rotating tip under it. It is an iframe so it keeps animating while Python is blocked in a stage.
RESEARCH_TIPS = [
    "Reading Reddit so you don't have to",
    "Skimming a hundred vlogs at 2x speed",
    "Sorting posts by how recent they are",
    "Ignoring the guidebook",
    'Turning "omg you HAVE to go" into a time slot',
    "Skipping the place everyone calls overrated",
    "Counting how many people mentioned that ramen",
    'Guessing what "near the station" means',
    "Drafting five days that don't start at 6am",
    "Leaving room for a second breakfast",
]
VERIFY_TIPS = [
    "Checking if the ramen place opens on Mondays",
    "Asking Google whether that bar still exists",
    "Measuring the walk from the shrine to the sushi counter",
    "Rejecting a museum that closes on Tuesdays",
    "Swapping the closed one for the one next door",
    "Counting minutes between stops, all of them",
    "Refusing to book anything without your say-so",
    "Politely waiting for Duffel",
    "Choosing the flight that isn't 19,455 EUR",
    "Making sure day three doesn't end in Yokohama",
]
LOADER_HTML = """
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap">
<style>
  body { margin: 0; background: transparent; font-family: "Press Start 2P", monospace; color: #14171C; }
  .wrap { padding: 8px 4px 0 4px; }
  .label { font-size: 11px; margin: 0 0 12px 0; letter-spacing: 0.02em; }
  .track {
    height: 22px; border: 3px solid #14171C; background: #6B7280; box-shadow: inset 0 -5px 0 #4B5563;
    image-rendering: pixelated;
  }
  .fill {
    height: 100%; width: 4%; background: #22C55E; box-shadow: inset 0 -5px 0 #15803D, inset 0 5px 0 #86EFAC;
    animation: fill __SECONDS__s steps(46, end) forwards;
  }
  @keyframes fill { from { width: 4%; } to { width: 94%; } }
  .tip { font-size: 9px; color: #5B6470; margin: 12px 0 0 0; line-height: 1.7; min-height: 30px; }
  .tip::after { content: "_"; animation: blink 1s steps(1) infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .fill { animation-duration: 0.1s; } .tip::after { animation: none; } }
</style>
<div class="wrap">
  <p class="label">__LABEL__</p>
  <div class="track"><div class="fill"></div></div>
  <p class="tip" id="tip"></p>
</div>
<script>
  const tips = __TIPS__;
  let order = tips.map((_, i) => i).sort(() => Math.random() - 0.5);
  let at = 0;
  const el = document.getElementById("tip");
  function next() { el.textContent = tips[order[at % order.length]]; at += 1; }
  next();
  setInterval(next, 2600);
</script>
"""


def main() -> None:
    load_dotenv()
    st.set_page_config(page_title="Trip agent", layout="wide")
    st.html(STYLE_BLOCK)
    if "tools" not in st.session_state:
        st.session_state["tools"] = build_tools()
    tools: Tools = st.session_state["tools"]
    slot = st.empty()  # the loading bar, at the top of the main column while a stage runs
    with st.sidebar:
        brief_form(tools, slot)
        state = current_state()
        if state is not None and state.report is None:
            questions_form(state, tools, slot)
        if state is not None:
            signals_list(state)
    state = current_state()
    if state is None or state.itinerary is None:
        hero()
        step_indicator(state)
        st.info("Fill in the brief on the left, then press Plan trip.")
    elif state.report is None:
        hero()
        step_indicator(state)
        draft_view(state)
    else:
        plan_view(state, tools)


def loader(label: str, tips: list[str], seconds: int) -> None:
    """Rendered inside the main-column slot; the sidebar form stays put underneath the user's hand."""
    body = (
        LOADER_HTML.replace("__LABEL__", esc(label))
        .replace("__TIPS__", json.dumps(tips))
        .replace("__SECONDS__", str(seconds))
    )
    components.html(body, height=120)


def hero() -> None:
    st.markdown(
        '<div class="hero">'
        '<p class="hero-kicker">Trip agent</p>'
        '<h1 class="hero-title">Where next?</h1>'
        '<p class="hero-tag">A plan built from what people posted this month, checked against real opening '
        "hours and travel times, booked only when you say so.</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def banner(state: TripState) -> None:
    brief = state.brief
    photo = next((place.photo_url for place in state.places.values() if place.photo_url), None)
    image = f'<img src="{esc(photo)}" alt="">' if photo else ""
    nights = brief.nights
    st.markdown(
        f'<div class="banner">{image}'
        '<div class="banner-text">'
        f'<h1 class="banner-title">{esc(brief.destination)}</h1>'
        f'<p class="banner-sub">{brief.start_date:%d %b} to {brief.end_date:%d %b} · {nights} nights · '
        f"{brief.travellers} travellers · {esc(budget_label(brief))}</p>"
        "</div></div>",
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
        ("Dates", f"{brief.start_date:%d %b} to {brief.end_date:%d %b}"),
        ("Travellers", str(brief.travellers)),
        ("Budget", budget_label(brief)),
        ("Departs in", departure_countdown(brief.start_date)),
    ]
    body = "".join(
        f'<div class="trip-cell"><span class="trip-cell-label">{esc(label)}</span>'
        f'<span class="trip-cell-value">{esc(value)}</span></div>'
        for label, value in cells
    )
    st.markdown(f'<div class="trip-strip">{body}</div>', unsafe_allow_html=True)


def budget_band(per_day: int) -> BudgetBand:
    if per_day < BUDGET_LOW_BELOW:
        return BudgetBand.low
    if per_day < BUDGET_HIGH_FROM:
        return BudgetBand.mid
    return BudgetBand.high


def budget_label(brief: TripBrief) -> str:
    answer = brief.answers.get(BUDGET_QUESTION, "")
    match = re.search(r"(\d+) EUR", answer)
    return f"{match.group(1)} EUR/day, {brief.budget_band.value}" if match else brief.budget_band.value


def split_code(pick: str) -> tuple[str, str]:
    """ "Tokyo (TYO)" -> ("Tokyo", "TYO"); a bare "TYO" -> ("TYO", "TYO"); anything else -> ("", "")."""
    match = re.fullmatch(r"\s*(.+?)\s*\(([A-Za-z]{3})\)\s*", pick)
    if match:
        return match.group(1), match.group(2).upper()
    if re.fullmatch(r"\s*[A-Za-z]{3}\s*", pick):
        return pick.strip().upper(), pick.strip().upper()
    return "", ""


def trim(text: str, limit: int = TITLE_CHARS) -> str:
    """Cuts at a word boundary and drops the noise titles carry: pipes, bracketed tags, emoji, runs of caps."""
    clean = re.sub(r"[\[\(【][^\]\)】]*[\]\)】]", " ", text)
    clean = re.sub(r"[|｜•·]+.*$", "", clean).strip()
    clean = re.sub(r"[^\w\s,.'’&:!?$€£¥-]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip() or text.strip()
    if clean.isupper() and len(clean) > 12:
        clean = string.capwords(clean)
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0].rstrip(",.:;-")
    return f"{cut}…"


def esc(value: object) -> str:
    return html.escape(str(value))


def current_state() -> TripState | None:
    state = st.session_state.get("state")
    return state if isinstance(state, TripState) else None


def log_for(state: TripState) -> CallLog:
    return CallLog(Path("logs/calls.jsonl"), state.brief.id)


def brief_form(tools: Tools, slot: DeltaGenerator) -> None:
    st.subheader("Where to?")
    with st.form("brief"):
        destination_pick = st.selectbox(
            "Destination",
            DESTINATIONS,
            index=DESTINATIONS.index("Tokyo (TYO)"),
            accept_new_options=True,
            help="Type to search. Not listed? Type it as City (IATA code), e.g. Porto (OPO).",
        )
        origin_pick = st.selectbox(
            "Flying from",
            ORIGINS,
            index=ORIGINS.index("Stockholm Arlanda (ARN)"),
            accept_new_options=True,
            help="Type to search. Not listed? Type it as Airport (IATA code).",
        )
        start = st.date_input("Start", dt.date(2026, 11, 12))
        end = st.date_input("End", dt.date(2026, 11, 16))
        travellers = st.number_input("Travellers", min_value=1, max_value=8, value=2)
        budget = st.slider(
            "Budget per person per day (EUR)",
            min_value=BUDGET_MIN,
            max_value=BUDGET_MAX,
            value=150,
            step=10,
            help="Food, tickets and getting around, flights aside. Under 100 reads as low, over 250 as high.",
        )
        styles = st.pills(
            "Styles",
            list(STYLES),
            selection_mode="multi",
            default=["food", "art"],
            format_func=lambda style: f"{STYLES[style]} {style}",
        )
        submitted = st.form_submit_button("Plan trip", type="primary", width="stretch")
    destination, destination_code = split_code(destination_pick or "")
    _, origin = split_code(origin_pick or "")
    if submitted and not (destination and destination_code and origin):
        st.error("Pick a destination and a departure airport, or type them as City (CODE).")
        submitted = False
    if submitted and isinstance(start, dt.date) and isinstance(end, dt.date):
        brief = TripBrief(
            id=f"ui-{re.sub(r'[^a-z0-9]+', '-', destination.lower())}-{start:%Y%m%d}",
            destination=destination,
            origin=origin,
            destination_code=destination_code.strip() or None,
            start_date=start,
            end_date=end,
            travellers=int(travellers),
            budget_band=budget_band(int(budget)),
            styles=list(styles),
            answers={BUDGET_QUESTION: f"about {int(budget)} EUR per person per day, flights aside"},
        )
        state = TripState(brief=brief)
        with slot.container():
            loader("Reading the internet about " + brief.destination, RESEARCH_TIPS, seconds=60)
        state = stage_draft(stage_research(state, tools, log_for(state)), tools, log_for(state))
        slot.empty()
        st.session_state["state"] = state
        st.rerun()


def questions_form(state: TripState, tools: Tools, slot: DeltaGenerator) -> None:
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
        go = st.form_submit_button("Check and finish the plan", type="primary", width="stretch")
    if go:
        with slot.container():
            loader("Checking every stop", VERIFY_TIPS, seconds=50)
        state = stage_verify(stage_refine(state, tools, log_for(state), answers), tools, log_for(state))
        state = stage_calendar(stage_search(state, tools, log_for(state)), tools, log_for(state))
        slot.empty()
        st.session_state["state"] = state
        st.rerun()


def source_line(signal: Signal) -> str:
    when = "" if signal.posted_at is None else f"{signal.posted_at:%d %b}"
    badge = SOURCE_LABEL.get(signal.source.value, signal.source.value[:3].upper())
    return (
        f'<a class="src" href="{esc(signal.url)}" target="_blank" rel="noopener" title="{esc(signal.title)}">'
        f'<span class="src-badge" data-source="{esc(signal.source.value)}">{esc(badge)}</span>'
        f'<span class="src-title">{esc(trim(signal.title))}</span>'
        f'<span class="src-date">{esc(when)}</span></a>'
    )


def signals_list(state: TripState) -> None:
    st.subheader("Drafted from")
    shown = state.signals[:14]
    st.markdown(
        f'<p class="src-count">{len(state.signals)} recent posts, newest and most relevant first</p>'
        f'<div class="src-list">{"".join(source_line(signal) for signal in shown)}</div>',
        unsafe_allow_html=True,
    )


def itinerary_view(state: TripState) -> None:
    if state.itinerary is None:
        return
    with_photos = any(place.photo_url for place in state.places.values())
    for day in state.itinerary.days:
        rows = []
        for stop in day.stops:
            reason = f' title="{esc(stop.failure_reason)}"' if stop.failure_reason else ""
            status = esc(stop.status.value)
            place = state.places.get(stop.place_id) if stop.place_id else None
            photo = (
                f'<img src="{esc(place.photo_url)}" alt="{esc(stop.place_name)}" loading="lazy">'
                if place is not None and place.photo_url
                else "<span></span>"
            )
            photo_cell = f'<td class="stop-photo">{photo}</td>' if with_photos else ""
            rows.append(
                "<tr>"
                f"{photo_cell}"
                f'<td class="stop-time">{stop.start:%H:%M}–{stop.end:%H:%M}</td>'
                "<td>"
                f'<span class="stop-place">{esc(stop.place_name)}</span>'
                f'<span class="stop-cat">{esc(stop.category)}</span>'
                f'<span class="stop-status" data-status="{status}"{reason}>{status}</span>'
                f'<p class="stop-why">{esc(stop.why)}</p>'
                "</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="day-block">'
            f'<div class="day-title">{day.date:%A} <small>{day.date:%d %B} · {len(day.stops)} stops</small></div>'
            f'<table class="manifest"><tbody>{"".join(rows)}</tbody></table>'
            "</div>",
            unsafe_allow_html=True,
        )


def draft_view(state: TripState) -> None:
    assert state.itinerary is not None
    st.subheader(f"{state.brief.destination}, first draft")
    st.caption("Nothing is checked yet. Answer the questions on the left to verify and finish it.")
    trip_strip(state)
    itinerary_view(state)


def plan_view(state: TripState, tools: Tools) -> None:
    assert state.itinerary is not None and state.report is not None
    banner(state)
    step_indicator(state)
    stat, swaps = st.columns([1, 3])
    stat.markdown(
        f'<div class="stat"><span class="stat-label">Stops verified</span>'
        f'<span class="stat-value">{state.report.pass_rate():.0%}</span></div>',
        unsafe_allow_html=True,
    )
    if state.replacements:
        items = []
        for swap in state.replacements:
            took = f"swapped for <b>{esc(swap.new.place_name)}</b>" if swap.new else "removed"
            why = swap.reason.split(": ", 1)[-1]
            items.append(
                f'<div class="swap"><span class="swap-old">{esc(swap.old.place_name)}</span>'
                f'<span class="swap-new">{took} <span class="swap-why">· {esc(why)}</span></span></div>'
            )
        swaps.markdown(f'<div class="swap-list">{"".join(items)}</div>', unsafe_allow_html=True)
    else:
        swaps.markdown(
            '<div class="swap-list"><div class="swap">Every stop passed first time.</div></div>', unsafe_allow_html=True
        )
    itinerary_view(state)
    st.subheader("Book")
    for option in state.options:
        with st.container(key=f"ticket-{option.provider_ref}"):
            kind_col, info_col, action_col = st.columns([0.7, 3.3, 1])
            kind_col.markdown(f'<span class="ticket-kind">{esc(option.kind.value)}</span>', unsafe_allow_html=True)
            info_col.markdown(
                f'<span class="ticket-price">{option.price_minor / 100:,.0f} {esc(option.currency)}</span>'
                f'<span class="ticket-sub">{esc(option.title)}</span>',
                unsafe_allow_html=True,
            )
            if action_col.button("Book", key=option.provider_ref, type="primary", width="stretch"):
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
