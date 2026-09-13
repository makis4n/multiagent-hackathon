import datetime as dt

from trip_core.models import Day, Itinerary, Stop
from trip_itinerary.schemas import FlatPatch, FlatStop, PatchesResponse, QuestionsResponse, to_patches

SIGNAL_IDS = ["sig-1", "sig-2"]


def itinerary() -> Itinerary:
    stops = [
        Stop(
            id=f"stop-{index:02d}",
            day=0,
            start=dt.time(9 + index),
            end=dt.time(10 + index),
            place_name=f"Place {index}",
            category="sight",
            why="A signal said so.",
        )
        for index in range(2)
    ]
    return Itinerary(
        id="it-1",
        brief_id="brief-1",
        days=[Day(date=dt.date(2026, 5, 1), stops=stops), Day(date=dt.date(2026, 5, 2))],
    )


def flat_stop(**overrides: object) -> FlatStop:
    fields: dict[str, object] = {
        "id": "stop-new",
        "day": 1,
        "start": "09:00",
        "end": "10:30",
        "place_name": "Kiyosumi Garden",
        "category": "nature",
        "why": "Two threads called it the calmest morning in the city.",
        "signal_ids": ["sig-1"],
    }
    fields.update(overrides)
    return FlatStop.model_validate(fields)


def test_questions_schema_holds_only_strings() -> None:
    response = QuestionsResponse.model_validate({"questions": ["Anything to skip?"]})
    assert response.questions == ["Anything to skip?"]
    assert list(QuestionsResponse.model_fields) == ["questions"]


def test_maps_one_well_formed_patch_of_each_op() -> None:
    response = PatchesResponse(
        patches=[
            FlatPatch(op="add", stop=flat_stop(), target_day=1, position=0),
            FlatPatch(op="remove", stop_id="stop-00"),
            FlatPatch(op="move", stop_id="stop-01", target_day=1),
            FlatPatch(op="replace", stop_id="stop-01", stop=flat_stop(id="stop-swap")),
        ]
    )
    result = to_patches(response, itinerary(), SIGNAL_IDS)
    assert result.dropped == []
    assert [patch.op for patch in result.patches] == ["add", "remove", "move", "replace"]
    added = result.patches[0]
    assert added.stop is not None
    assert added.stop.start == dt.time(9, 0)
    assert added.stop.end == dt.time(10, 30)
    assert added.target_day == 1
    assert added.position == 0


def test_a_bad_time_string_drops_the_patch_without_raising() -> None:
    response = PatchesResponse(
        patches=[
            FlatPatch(op="add", stop=flat_stop(start="half nine"), target_day=1),
            FlatPatch(op="remove", stop_id="stop-00"),
        ]
    )
    result = to_patches(response, itinerary(), SIGNAL_IDS)
    assert [patch.op for patch in result.patches] == ["remove"]
    assert len(result.dropped) == 1
    assert "half nine" in result.dropped[0]


def test_an_unknown_op_is_rejected() -> None:
    result = to_patches(PatchesResponse(patches=[FlatPatch(op="reschedule", stop_id="stop-00")]), itinerary(), [])
    assert result.patches == []
    assert "unknown op" in result.dropped[0]


def test_a_signal_id_that_was_never_passed_in_is_stripped() -> None:
    response = PatchesResponse(
        patches=[FlatPatch(op="add", stop=flat_stop(signal_ids=["sig-1", "sig-99"]), target_day=1)]
    )
    result = to_patches(response, itinerary(), SIGNAL_IDS)
    assert result.dropped == []
    stop = result.patches[0].stop
    assert stop is not None
    assert stop.signal_ids == ["sig-1"]


def test_an_op_that_names_no_stop_is_dropped() -> None:
    result = to_patches(PatchesResponse(patches=[FlatPatch(op="remove", stop_id="stop-99")]), itinerary(), SIGNAL_IDS)
    assert result.patches == []
    assert "stop-99" in result.dropped[0]


def test_the_itinerary_passed_in_is_never_touched() -> None:
    original = itinerary()
    to_patches(PatchesResponse(patches=[FlatPatch(op="remove", stop_id="stop-00")]), original, SIGNAL_IDS)
    assert [stop.id for stop in original.stops()] == ["stop-00", "stop-01"]
    assert original.version == 1
