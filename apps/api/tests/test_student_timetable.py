"""Student Show Timetable — checks 3.1 to 3.8 of the prompt.

The fixture is built from real shapes rather than a happy path: one intake with
several units, a break, an assessment week, a clustered unit, an unresolved
campus, an unresolved unit, a quarantined delivery, and a unit with no
allocation at all. Each exists to catch one of the faults these checks are for.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import event, select, text

from app.models.student import Student
from app.services.student_timetable import student_timetable
from app.services.students import StudentServiceError

pytestmark = pytest.mark.database

LABEL = "BSB50420_52_19 Jan 2026_NA_Intake"
OTHER_LABEL = "BSB50420_52_02 Feb 2026_NA_Intake"
MONDAY = dt.date(2026, 1, 19)


def _monday(offset_weeks: int) -> dt.date:
    return MONDAY + dt.timedelta(days=7 * offset_weeks)


@pytest.fixture()
def world(session):
    """Two campuses, one shared intake label, and every awkward shape."""
    session.execute(
        text(
            "TRUNCATE TABLE allocation_session, allocation_delivery_intake, allocation_delivery, "
            "rolling_timetable_weeks, students, student_groups, course_offerings, "
            "college_campuses, campuses, colleges, facilities, units, qualifications, "
            "course_statuses RESTART IDENTITY CASCADE"
        )
    )
    college = session.execute(
        text(
            "INSERT INTO colleges (college_short_name, college_full_name, is_active) "
            "VALUES ('TT', 'Timetable College', true) RETURNING id"
        )
    ).scalar_one()
    campus_a = session.execute(
        text(
            "INSERT INTO campuses (campus_code, campus_name, campus_location, state, is_active) "
            "VALUES ('TTA', 'Sydney', 'Sydney CBD', 'NSW', true) RETURNING id"
        )
    ).scalar_one()
    campus_b = session.execute(
        text(
            "INSERT INTO campuses (campus_code, campus_name, campus_location, state, is_active) "
            "VALUES ('TTB', 'Melbourne', 'Melbourne CBD', 'VIC', true) RETURNING id"
        )
    ).scalar_one()
    for campus in (campus_a, campus_b):
        session.execute(
            text("INSERT INTO college_campuses (college_id, campus_id, is_active) VALUES (:c, :p, true)"),
            {"c": college, "p": campus},
        )
    qual = session.execute(
        text(
            "INSERT INTO qualifications (qualification_code, qualification_title, is_active) "
            "VALUES ('BSB50420', 'Diploma of Leadership', true) RETURNING id"
        )
    ).scalar_one()
    status_id = session.execute(
        text(
            "INSERT INTO course_statuses (code, label, selectable_for_new_records, is_active) "
            "VALUES ('ACTIVE', 'Active', true, true) RETURNING id"
        )
    ).scalar_one()
    offering = session.execute(
        text(
            "INSERT INTO course_offerings (college_id, campus_id, qualification_id, course_code, course_status_id) "
            "VALUES (:c, :p, :q, 'BSB50420-SYD', :s) RETURNING id"
        ),
        {"c": college, "p": campus_a, "q": qual, "s": status_id},
    ).scalar_one()
    unit_one = session.execute(
        text("INSERT INTO units (unit_code, unit_title, is_active) VALUES ('BSBOPS501', 'Operational plan', true) RETURNING id")
    ).scalar_one()
    facility = session.execute(
        text(
            "INSERT INTO facilities (facility_reference, campus_id, source_location, facility_type, capacity, is_active) "
            "VALUES ('Room 1', :p, '', 'Classroom', 30, true) RETURNING id"
        ),
        {"p": campus_a},
    ).scalar_one()
    group = session.execute(
        text(
            "INSERT INTO student_groups (group_code, course_offering_id, intake, rolling_intake_label, is_active) "
            "VALUES ('NA', :o, :i, :label, true) RETURNING id"
        ),
        {"o": offering, "i": MONDAY, "label": LABEL},
    ).scalar_one()

    # -- The rolling timetable: what this intake studies --------------------
    # w1-3 BSBOPS501 · w4 BREAK · w5-6 BSBOPS501 (resumes) · w7 ASSESSMENT
    # w8 clustered unit · w9 unresolved-unit · w10 unit with no allocation
    weeks = [
        (1, "UNIT", "BSBOPS501", "BSBOPS501", 1),
        (2, "UNIT", "BSBOPS501", "BSBOPS501", 1),
        (3, "UNIT", "BSBOPS501", "BSBOPS501", 1),
        (4, "BREAK", "Break", None, 1),
        (5, "UNIT", "BSBOPS501", "BSBOPS501", 1),
        (6, "UNIT", "BSBOPS501", "BSBOPS501", 1),
        (7, "ASSESSMENT_WEEK", "Assessment Week", None, 1),
        (8, "UNIT", "FNSACC522/FNSACC526", "FNSACC522/FNSACC526", 1),
        (9, "UNIT", "BSBOPS502", "BSBOPS502", 1),
        (10, "UNIT", "BSBLONELY", "BSBLONELY", 1),
    ]
    for week_no, kind, value, code, slot in weeks:
        start = _monday(week_no - 1)
        session.execute(
            text(
                "INSERT INTO rolling_timetable_weeks "
                "(training_package, qualification_code, duration_weeks, intake_label, intake_group, "
                " intake_start_date, week_no, week_start_date, week_end_date, schedule_type, "
                " schedule_value, unit_code, unit_count, unit_slot) "
                "VALUES ('BSB', 'BSB50420', 52, :label, 'NA', :istart, :wno, :ws, :we, :kind, "
                " :value, :code, :count, :slot)"
            ),
            {
                "label": LABEL,
                "istart": MONDAY,
                "wno": week_no,
                "ws": start,
                "we": start + dt.timedelta(days=6),
                "kind": kind,
                "value": value,
                "code": code,
                "count": 1 if code else 0,
                "slot": slot,
            },
        )

    ids = {
        "college": college,
        "campus_a": campus_a,
        "campus_b": campus_b,
        "qual": qual,
        "offering": offering,
        "unit_one": unit_one,
        "facility": facility,
        "group": group,
    }

    student = Student(
        student_id="TT0001",
        first_name="Tess",
        last_name="Timetable",
        coe_status="COE",
        ct_student=False,
        status="ACTIVE",
        intake_match_status="MATCHED",
        proposed_start_date=MONDAY,
        proposed_end_date=MONDAY + dt.timedelta(days=7 * 9),
        college_email="tt0001@x.test",
        course_offering_id=offering,
        student_group_id=group,
    )
    session.add(student)
    session.flush()
    ids["student"] = student.id
    session.commit()
    return ids


def _delivery(
    session,
    ids,
    *,
    unit_id=None,
    unit_text=None,
    start_week=0,
    end_week=2,
    campus_id="A",
    campus_text=None,
    college_id="SET",
    college_text=None,
    quarantined=False,
    weekdays=("MONDAY", "TUESDAY"),
    stream="THEORY",
    facility=True,
    label=LABEL,
):
    """One delivery for the intake, with a session per named weekday."""
    campus = ids["campus_a"] if campus_id == "A" else (ids["campus_b"] if campus_id == "B" else None)
    college = ids["college"] if college_id == "SET" else None
    delivery_id = session.execute(
        text(
            "INSERT INTO allocation_delivery "
            "(training_package, college_id, campus_id, qualification_id, duration_weeks, group_code, "
            " unit_id, unit_text, uoc_type, mode_of_delivery, start_date, end_date, "
            " intake_match_status, is_quarantined, campus_text, college_text) "
            "VALUES ('BSB', :college, :campus, :qual, 52, 'NA', :unit, :utext, 'THEORY_ONLY', 'F2FP', "
            " :start, :end, 'MATCHED', :quar, :ctext, :cotext) RETURNING id"
        ),
        {
            "college": college,
            "campus": campus,
            "qual": ids["qual"],
            "unit": unit_id,
            "utext": unit_text,
            "start": _monday(start_week),
            "end": _monday(end_week) + dt.timedelta(days=6),
            "quar": quarantined,
            "ctext": campus_text,
            "cotext": college_text,
        },
    ).scalar_one()
    session.execute(
        text(
            "INSERT INTO allocation_delivery_intake (delivery_id, training_package, intake_label, group_code) "
            "VALUES (:d, 'BSB', :label, 'NA')"
        ),
        {"d": delivery_id, "label": label},
    )
    for weekday in weekdays:
        session.execute(
            text(
                "INSERT INTO allocation_session "
                "(training_package, delivery_id, stream, weekday, start_time, end_time, "
                " delivery_mode, facility_id, classroom_text) "
                "VALUES ('BSB', :d, :stream, :wd, TIME '09:00', TIME '17:00', "
                " :mode, :fac, :ctext)"
            ),
            {
                "d": delivery_id,
                "stream": stream,
                "wd": weekday,
                "mode": "VIRTUAL" if stream == "MSCRIS" else "PHYSICAL",
                "fac": ids["facility"] if facility else None,
                "ctext": None if facility else "Old Room Name",
            },
        )
    session.commit()
    return delivery_id


def _rows(payload, row_type="UNIT"):
    return [row for row in payload["rows"] if row["row_type"] == row_type]


def _unit(payload, code):
    return next((row for row in _rows(payload) if row["unit_code"] == code), None)


# ---------------------------------------------------------------------------
# 3.1 The join chain
# ---------------------------------------------------------------------------


def test_j1_a_matched_student_gets_their_units_and_classes(session, world):
    _delivery(session, world, unit_id=world["unit_one"])
    payload = student_timetable(session, world["student"])

    assert payload["empty_reason"] is None
    unit = _unit(payload, "BSBOPS501")
    assert unit is not None
    assert unit["allocation_status"] == "ALLOCATED"
    assert unit["classes"], "an allocated unit must carry its class rows"


def test_j2_only_the_students_own_campus_is_returned(session, world):
    """The same intake label runs at two campuses; only the student's may show."""
    _delivery(session, world, unit_id=world["unit_one"], campus_id="A")
    _delivery(session, world, unit_id=world["unit_one"], campus_id="B", weekdays=("WEDNESDAY",))

    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    weekdays = {item["weekday"] for item in unit["classes"]}
    assert "WEDNESDAY" not in weekdays, "a Melbourne class must not reach a Sydney student"
    assert weekdays == {"MONDAY", "TUESDAY"}


def test_j3_an_unresolved_campus_is_still_shown(session, world):
    _delivery(session, world, unit_id=world["unit_one"], campus_id=None)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["allocation_status"] == "ALLOCATED"
    assert all(item["campus_unresolved"] is True for item in unit["classes"])


def test_j4_resolving_that_campus_to_the_students_own_keeps_it(session, world):
    """J4 — corrects itself with no re-import and no cached copy."""
    delivery_id = _delivery(session, world, unit_id=world["unit_one"], campus_id=None)
    session.execute(
        text("UPDATE allocation_delivery SET campus_id = :c WHERE id = :i"),
        {"c": world["campus_a"], "i": delivery_id},
    )
    session.commit()

    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["allocation_status"] == "ALLOCATED"
    assert all(item["campus_unresolved"] is False for item in unit["classes"])
    assert all(item["campus"] == "Sydney" for item in unit["classes"])


def test_j5_resolving_it_to_a_different_campus_removes_it(session, world):
    delivery_id = _delivery(session, world, unit_id=world["unit_one"], campus_id=None)
    session.execute(
        text("UPDATE allocation_delivery SET campus_id = :c WHERE id = :i"),
        {"c": world["campus_b"], "i": delivery_id},
    )
    session.commit()

    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["allocation_status"] == "UNALLOCATED", "another campus's class must drop away"


def test_j6_an_unresolved_college_is_still_shown(session, world):
    _delivery(session, world, unit_id=world["unit_one"], college_id=None)
    payload = student_timetable(session, world["student"])
    assert _unit(payload, "BSBOPS501")["allocation_status"] == "ALLOCATED"


def test_j8_an_unresolved_campus_naming_another_campus_is_not_shown(session, world):
    """The reported defect: a class recorded at "Melbourne" on a Sydney timetable.

    The campus filter used to ask only whether the identifier was null. A
    delivery whose campus never resolved therefore reached **every** student of
    that intake, and the campus column said Melbourne while claiming to be
    theirs. An unresolved reference is matched on the text it was written as.
    """
    _delivery(
        session,
        world,
        unit_id=world["unit_one"],
        campus_id=None,
        campus_text="Melbourne",
        weekdays=("WEDNESDAY",),
    )
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["allocation_status"] == "UNALLOCATED"
    assert unit["classes"] == [], "another campus's class must not reach this student"


def test_j9_an_unresolved_campus_naming_the_students_own_is_shown(session, world):
    """Matched on the text, and still marked unresolved so the state is visible."""
    _delivery(session, world, unit_id=world["unit_one"], campus_id=None, campus_text="Sydney")
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["allocation_status"] == "ALLOCATED"
    assert all(item["campus"] == "Sydney" for item in unit["classes"])
    assert all(item["campus_unresolved"] is True for item in unit["classes"])


def test_j9b_the_text_match_ignores_case_and_inner_spacing(session, world):
    _delivery(session, world, unit_id=world["unit_one"], campus_id=None, campus_text="  sydney  ")
    payload = student_timetable(session, world["student"])
    assert _unit(payload, "BSBOPS501")["allocation_status"] == "ALLOCATED"


def test_j10_an_unresolved_college_naming_another_college_is_not_shown(session, world):
    """The same intake label runs for several colleges; only the student's shows."""
    _delivery(
        session,
        world,
        unit_id=world["unit_one"],
        college_id=None,
        college_text="Some Other College",
    )
    payload = student_timetable(session, world["student"])
    assert _unit(payload, "BSBOPS501")["allocation_status"] == "UNALLOCATED"


def test_j11_resolving_the_campus_suggestion_brings_the_class_back(session, world):
    """It corrects itself as the reference data improves, with no re-import."""
    delivery_id = _delivery(
        session, world, unit_id=world["unit_one"], campus_id=None, campus_text="Melbourne"
    )
    assert _unit(student_timetable(session, world["student"]), "BSBOPS501")["classes"] == []

    # An administrator maps "Melbourne" to this student's own campus.
    session.execute(
        text("UPDATE allocation_delivery SET campus_id = :c WHERE id = :i"),
        {"c": world["campus_a"], "i": delivery_id},
    )
    session.commit()

    unit = _unit(student_timetable(session, world["student"]), "BSBOPS501")
    assert unit["allocation_status"] == "ALLOCATED"
    assert all(item["campus_unresolved"] is False for item in unit["classes"])


def test_j7_a_quarantined_delivery_never_appears(session, world):
    _delivery(session, world, unit_id=world["unit_one"], quarantined=True)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["allocation_status"] == "UNALLOCATED"
    assert unit["classes"] == []


# ---------------------------------------------------------------------------
# 3.2 Nothing disappears
# ---------------------------------------------------------------------------


def test_n1_a_unit_with_no_allocation_still_appears(session, world):
    payload = student_timetable(session, world["student"])
    lonely = _unit(payload, "BSBLONELY")
    assert lonely is not None
    assert lonely["allocation_status"] == "UNALLOCATED"


def test_n3_a_delivery_with_an_unresolved_unit_matches_on_text(session, world):
    """N3 — matching on `unit_id` would leave this orphaned and wrongly grey."""
    _delivery(session, world, unit_id=None, unit_text="BSBOPS502", start_week=8, end_week=8)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS502")
    assert unit["allocation_status"] == "ALLOCATED"
    assert unit["classes"], "the class exists and must attach to the unit the student studies"


def test_n4_resolving_that_unit_keeps_it_allocated(session, world):
    delivery_id = _delivery(session, world, unit_id=None, unit_text="BSBOPS502", start_week=8, end_week=8)
    unit_two = session.execute(
        text("INSERT INTO units (unit_code, unit_title, is_active) VALUES ('BSBOPS502', 'Plan resources', true) RETURNING id")
    ).scalar_one()
    session.execute(
        text("UPDATE allocation_delivery SET unit_id = :u WHERE id = :i"),
        {"u": unit_two, "i": delivery_id},
    )
    session.commit()

    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS502")
    assert unit["allocation_status"] == "ALLOCATED"
    assert unit["unit_title"] == "Plan resources"


def test_n5_a_clustered_unit_is_one_row_on_the_slash_form(session, world):
    _delivery(session, world, unit_id=None, unit_text="FNSACC522/FNSACC526", start_week=7, end_week=7)
    payload = student_timetable(session, world["student"])
    clustered = [row for row in _rows(payload) if row["unit_code"] == "FNSACC522/FNSACC526"]
    assert len(clustered) == 1, "a clustered unit is one unit, not two"
    assert clustered[0]["allocation_status"] == "ALLOCATED"


def test_n7_units_total_matches_the_rolling_groups(session, world):
    payload = student_timetable(session, world["student"])
    # BSBOPS501 (grouped across the break), the clustered unit, BSBOPS502, BSBLONELY.
    assert payload["summary"]["units_total"] == 4
    assert payload["summary"]["units_total"] == len(_rows(payload))


# ---------------------------------------------------------------------------
# 3.3 Class expansion
# ---------------------------------------------------------------------------


def test_e1_three_weeks_on_two_days_is_six_class_rows(session, world):
    _delivery(session, world, unit_id=world["unit_one"], start_week=0, end_week=2)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert len(unit["classes"]) == 6, "one row per real class, not per week"


def test_e2_every_date_is_in_range_and_on_the_right_weekday(session, world):
    _delivery(session, world, unit_id=world["unit_one"], start_week=0, end_week=2)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    for item in unit["classes"]:
        assert _monday(0) <= item["date"] <= _monday(2) + dt.timedelta(days=6)
        assert item["date"].strftime("%A").upper() == item["weekday"]


def test_e3_an_mscris_session_is_saturday_and_virtual(session, world):
    _delivery(
        session, world, unit_id=world["unit_one"], weekdays=("SATURDAY",), stream="MSCRIS", facility=False
    )
    payload = student_timetable(session, world["student"])
    classes = _unit(payload, "BSBOPS501")["classes"]
    assert classes and all(item["weekday"] == "SATURDAY" for item in classes)
    assert all(item["stream"] == "MSCRIS" for item in classes)
    assert all(item["delivery_mode"] == "VIRTUAL" for item in classes)


def test_e5_e6_a_diverging_span_is_noted_and_the_delivery_dates_win(session, world):
    """E5/E6 — the allocation is the real booking, so its dates are used."""
    _delivery(session, world, unit_id=world["unit_one"], start_week=20, end_week=21)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["span_note"], "a materially different range must be named, not silently chosen"
    for item in unit["classes"]:
        assert item["date"] >= _monday(20), "class rows follow the delivery, not the rolling span"


def test_e7_a_runaway_range_is_refused(session, world):
    _delivery(session, world, unit_id=world["unit_one"], start_week=0, end_week=70)
    payload = student_timetable(session, world["student"])
    unit = _unit(payload, "BSBOPS501")
    assert unit["expansion_refused"] is True
    assert unit["classes"] == []
    assert unit["span_note"]


def test_e8_a_delivery_with_no_sessions_is_unallocated(session, world):
    delivery_id = _delivery(session, world, unit_id=world["unit_one"])
    session.execute(text("DELETE FROM allocation_session WHERE delivery_id = :d"), {"d": delivery_id})
    session.commit()
    payload = student_timetable(session, world["student"])
    assert _unit(payload, "BSBOPS501")["allocation_status"] == "UNALLOCATED"


# ---------------------------------------------------------------------------
# 3.4 Breaks and assessment weeks
# ---------------------------------------------------------------------------


def test_b1_b2_a_break_is_one_collapsed_row_with_no_classes(session, world):
    payload = student_timetable(session, world["student"])
    breaks = _rows(payload, "BREAK")
    assert len(breaks) == 1
    assert breaks[0]["classes"] == []
    assert breaks[0]["unit_code"] is None


def test_b4_assessment_weeks_collapse_the_same_way(session, world):
    payload = student_timetable(session, world["student"])
    weeks = _rows(payload, "ASSESSMENT_WEEK")
    assert len(weeks) == 1
    assert weeks[0]["classes"] == []


def test_b5_a_unit_interrupted_by_a_break_stays_one_row(session, world):
    """B5 — a Break is not a UNIT row, so the same unit resuming continues it."""
    payload = student_timetable(session, world["student"])
    ops = [row for row in _rows(payload) if row["unit_code"] == "BSBOPS501"]
    assert len(ops) == 1, "weeks 1-3 and 5-6 are one delivery, not two"
    assert ops[0]["week_from"] == _monday(0)
    assert ops[0]["week_to"] == _monday(5) + dt.timedelta(days=6)


def test_b6_rows_are_ordered_by_week(session, world):
    payload = student_timetable(session, world["student"])
    starts = [row["week_from"] for row in payload["rows"]]
    assert starts == sorted(starts), "breaks must sit in their true chronological place"


# ---------------------------------------------------------------------------
# 3.5 Student dates
# ---------------------------------------------------------------------------


def test_p1_p2_p3_units_are_classified_against_the_students_dates(session, world):
    session.execute(
        text("UPDATE students SET proposed_start_date = :s, proposed_end_date = :e WHERE id = :i"),
        {"s": _monday(4), "e": _monday(8) + dt.timedelta(days=6), "i": world["student"]},
    )
    session.commit()

    payload = student_timetable(session, world["student"])
    # BSBOPS501 spans weeks 1-6, which includes the student's week-5 start.
    assert _unit(payload, "BSBOPS501")["timing"] == "DURING"
    # BSBLONELY is week 10, after the student's course ends.
    assert _unit(payload, "BSBLONELY")["timing"] == "AFTER_END"


def test_p1_a_unit_finishing_before_the_student_joined(session, world):
    session.execute(
        text("UPDATE students SET proposed_start_date = :s, proposed_end_date = :e WHERE id = :i"),
        {"s": _monday(8), "e": _monday(20), "i": world["student"]},
    )
    session.commit()
    payload = student_timetable(session, world["student"])
    assert _unit(payload, "BSBOPS501")["timing"] == "BEFORE_JOINING"


# ---------------------------------------------------------------------------
# 3.6 Empty states
# ---------------------------------------------------------------------------


def test_z1_credit_transfer(session, world):
    session.execute(
        text(
            "UPDATE students SET intake_match_status = 'NOT_APPLICABLE', ct_student = true, "
            "student_group_id = NULL WHERE id = :i"
        ),
        {"i": world["student"]},
    )
    session.commit()
    payload = student_timetable(session, world["student"])
    assert payload["empty_reason"] == "CREDIT_TRANSFER"
    assert payload["rows"] == []


def test_z2_no_rolling_timetable(session, world):
    session.execute(
        text("UPDATE students SET intake_match_status = 'TBD', student_group_id = NULL WHERE id = :i"),
        {"i": world["student"]},
    )
    session.commit()
    payload = student_timetable(session, world["student"])
    assert payload["empty_reason"] == "NO_ROLLING_TIMETABLE"
    # The message needs the qualification and duration to name them.
    assert payload["qualification"]["code"] == "BSB50420"


def test_z3_matched_but_no_rolling_rows(session, world):
    session.execute(text("DELETE FROM rolling_timetable_weeks"))
    session.commit()
    payload = student_timetable(session, world["student"])
    assert payload["empty_reason"] == "NO_ROLLING_ROWS"


def test_z5_matched_with_no_allocations_is_not_an_empty_state(session, world):
    payload = student_timetable(session, world["student"])
    assert payload["empty_reason"] is None
    assert payload["summary"]["units_total"] == 4
    assert payload["summary"]["units_allocated"] == 0
    assert all(row["allocation_status"] == "UNALLOCATED" for row in _rows(payload))


def test_z6_a_missing_student_is_404(session, world):
    with pytest.raises(StudentServiceError) as caught:
        student_timetable(session, 999999)
    assert caught.value.status_code == 404


# ---------------------------------------------------------------------------
# 3.7 Efficiency
# ---------------------------------------------------------------------------


def _count_queries(session, test_engine, student_pk):
    seen: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        student_timetable(session, student_pk)
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)
    return len(seen)


def test_q1_q2_the_query_count_is_exactly_three_and_does_not_scale(session, world, test_engine):
    """Q1/Q2 — three queries whether the intake is large or small."""
    _delivery(session, world, unit_id=world["unit_one"], start_week=0, end_week=2)
    session.expire_all()
    small = _count_queries(session, test_engine, world["student"])

    # Many more classes: three more deliveries, each with two weekdays.
    for start in (5, 7, 8):
        _delivery(session, world, unit_id=world["unit_one"], start_week=start, end_week=start + 1)
    session.expire_all()
    large = _count_queries(session, test_engine, world["student"])

    assert small == 3, f"expected exactly three queries, issued {small}"
    assert large == 3, f"the count must not scale with the data; issued {large}"


def test_q3_an_empty_state_costs_one_query(session, world, test_engine):
    session.execute(
        text("UPDATE students SET intake_match_status = 'TBD', student_group_id = NULL WHERE id = :i"),
        {"i": world["student"]},
    )
    session.commit()
    session.expire_all()
    assert _count_queries(session, test_engine, world["student"]) == 1


# ---------------------------------------------------------------------------
# 3.8 Correctness of shape
# ---------------------------------------------------------------------------


def test_c1_every_boolean_is_a_real_boolean(session, world):
    _delivery(session, world, unit_id=world["unit_one"], campus_id=None, facility=False)
    payload = student_timetable(session, world["student"])
    for row in payload["rows"]:
        assert isinstance(row["expansion_refused"], bool)
        for item in row["classes"]:
            assert isinstance(item["classroom_unresolved"], bool)
            assert isinstance(item["campus_unresolved"], bool)


def test_c2_a_null_qualification_does_not_raise(session, world):
    """C2 — the outer joins hold where the calendar's inner joins would drop it."""
    delivery_id = _delivery(session, world, unit_id=world["unit_one"])
    session.execute(
        text("UPDATE allocation_delivery SET qualification_id = NULL WHERE id = :i"), {"i": delivery_id}
    )
    session.commit()
    payload = student_timetable(session, world["student"])
    assert _unit(payload, "BSBOPS501")["allocation_status"] == "ALLOCATED"


def test_c3_an_unresolved_classroom_shows_the_text(session, world):
    _delivery(session, world, unit_id=world["unit_one"], facility=False)
    payload = student_timetable(session, world["student"])
    classes = _unit(payload, "BSBOPS501")["classes"]
    assert all(item["classroom"] == "Old Room Name" for item in classes)
    assert all(item["classroom_unresolved"] is True for item in classes)


def test_c5_no_classroom_at_all_reads_not_yet_allocated(session, world):
    delivery_id = _delivery(session, world, unit_id=world["unit_one"], facility=False)
    session.execute(
        text("UPDATE allocation_session SET classroom_text = NULL WHERE delivery_id = :d"),
        {"d": delivery_id},
    )
    session.commit()
    payload = student_timetable(session, world["student"])
    classes = _unit(payload, "BSBOPS501")["classes"]
    assert all(item["classroom"] == "Not yet allocated" for item in classes)
    assert all(item["classroom_unresolved"] is False for item in classes)


def test_c6_times_are_hh_mm_strings(session, world):
    _delivery(session, world, unit_id=world["unit_one"])
    payload = student_timetable(session, world["student"])
    for item in _unit(payload, "BSBOPS501")["classes"]:
        assert isinstance(item["start_time"], str)
        assert item["start_time"] == "09:00"
        assert item["end_time"] == "17:00"
