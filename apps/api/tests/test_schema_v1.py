"""Schema v1 verification tests.

These run against **PostgreSQL**, not SQLite: the approved schema uses native
enums, `citext`, a generated column, partial indexes, a deferrable constraint
and a composite foreign key, none of which SQLite can represent. Testing the
schema anywhere else would prove nothing about the database that actually runs.

The tests are read-only apart from the integrity tests, which insert into a
transaction that is always rolled back. They never seed data.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from app.db.session import DatabaseNotConfiguredError, get_engine
from app.models import EXPECTED_TABLES, EXPECTED_VIEWS, Base

pytestmark = pytest.mark.database


@pytest.fixture(scope="module")
def engine():
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except DatabaseNotConfiguredError as exc:  # pragma: no cover
        pytest.skip(f"database not configured: {exc}")
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unreachable: {type(exc).__name__}")
    return eng


@pytest.fixture()
def connection(engine):
    """A connection whose transaction is always rolled back."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------


def test_sqlalchemy_can_connect(engine):
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


def test_connected_to_a_development_database(engine):
    """Guard rail: these tests must never run against production."""
    with engine.connect() as conn:
        name = conn.execute(text("SELECT current_database()")).scalar_one()
    assert name.endswith("_dev") or "test" in name, f"unexpected database {name!r}"


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def test_model_metadata_matches_expected_inventory():
    """Catches a model module that was never imported in app/models/__init__."""
    assert set(Base.metadata.tables) == set(EXPECTED_TABLES)


def test_all_expected_tables_exist(engine):
    actual = set(inspect(engine).get_table_names(schema="public"))
    missing = set(EXPECTED_TABLES) - actual
    assert not missing, f"missing tables: {sorted(missing)}"


def test_no_unexpected_tables(engine):
    actual = set(inspect(engine).get_table_names(schema="public"))
    # alembic_version is Alembic bookkeeping, not a business table.
    extra = actual - set(EXPECTED_TABLES) - {"alembic_version"}
    assert not extra, f"unexpected tables: {sorted(extra)}"


def test_expected_views_exist(engine):
    actual = set(inspect(engine).get_view_names(schema="public"))
    missing = set(EXPECTED_VIEWS) - actual
    assert not missing, f"missing views: {sorted(missing)}"


def test_citext_extension_installed(engine):
    with engine.connect() as conn:
        installed = conn.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'citext'")
        ).scalar_one()
    assert installed == 1, "citext is required by the email columns"


# ---------------------------------------------------------------------------
# Columns — model metadata versus the live database
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table_name", EXPECTED_TABLES)
def test_columns_match_model(engine, table_name):
    """Every model column exists in PostgreSQL with the same nullability."""
    actual = {c["name"]: c for c in inspect(engine).get_columns(table_name, schema="public")}
    model = Base.metadata.tables[table_name]

    missing = set(model.columns.keys()) - set(actual)
    assert not missing, f"{table_name}: columns missing in database: {sorted(missing)}"

    extra = set(actual) - set(model.columns.keys())
    assert not extra, f"{table_name}: unexpected columns in database: {sorted(extra)}"

    for name, column in model.columns.items():
        assert actual[name]["nullable"] == column.nullable, (
            f"{table_name}.{name}: nullable mismatch — "
            f"model={column.nullable} database={actual[name]['nullable']}"
        )


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table_name", EXPECTED_TABLES)
def test_primary_key_exists(engine, table_name):
    pk = inspect(engine).get_pk_constraint(table_name, schema="public")
    assert pk["constrained_columns"], f"{table_name} has no primary key"


def test_expected_foreign_key_count(engine):
    insp = inspect(engine)
    total = sum(len(insp.get_foreign_keys(t, schema="public")) for t in EXPECTED_TABLES)
    # 54 from Schema v1 (relationship matrix + soft-delete columns on seven
    # tables), plus 2 from Access Model v1.1 (access_requests.requester_user_id
    # and access_requests.decided_by_user_id), plus 2 from the 14 August 2026
    # alias tables (campus_source_addresses.campus_id and
    # qualification_supersessions.qualification_id).
    assert total == 58, f"expected 58 foreign keys, found {total}"


def test_no_foreign_key_uses_set_null(engine):
    """Schema v1 §23: no SET NULL anywhere. Every nullable FK is genuinely optional."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname FROM pg_constraint WHERE contype = 'f' AND confdeltype = 'n'"
            )
        ).fetchall()
    assert not rows, f"unexpected ON DELETE SET NULL: {[r[0] for r in rows]}"


def test_cascade_deletes_only_where_approved(engine):
    """Only true compositions cascade (Schema v1 §23)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conrelid::regclass::text FROM pg_constraint "
                "WHERE contype = 'f' AND confdeltype = 'c'"
            )
        ).fetchall()
    actual = sorted({r[0] for r in rows})
    approved = sorted(
        {
            "offering_duration_options",
            "reason_code_contexts",
            "import_staged_rows",
            "campus_source_addresses",
            "import_row_issues",
            "trainer_availability",
            "trainer_qualifications",
            "trainer_units",
            "timetable_unit_deliveries",
            "timetable_sessions",
            "timetable_clash_overrides",
        }
    )
    assert actual == approved, f"cascade set differs — got {actual}"


@pytest.mark.parametrize(
    ("table_name", "constraint_name"),
    [
        ("students", "ck_students_course_dates_ordered"),
        ("students", "ck_students_soft_delete_metadata_complete"),
        ("facilities", "ck_facilities_capacity_positive"),
        ("offering_duration_options", "ck_offering_duration_options_duration_weeks_positive"),
        ("trainer_availability", "ck_trainer_availability_working_time_ordered"),
        ("timetable_sessions", "ck_timetable_sessions_session_times_ordered"),
        ("timetable_sessions", "ck_timetable_sessions_additional_sessions_are_virtual"),
        ("timetable_sessions", "ck_timetable_sessions_free_text_trainer_only_for_additional"),
        ("timetable_unit_deliveries", "ck_timetable_unit_deliveries_delivery_dates_ordered"),
        ("user_activity_records", "ck_user_activity_records_outcome_present"),
    ],
)
def test_approved_check_constraint_exists(engine, table_name, constraint_name):
    names = {c["name"] for c in inspect(engine).get_check_constraints(table_name, schema="public")}
    assert constraint_name in names, f"{table_name}: missing {constraint_name}; found {sorted(names)}"


@pytest.mark.parametrize(
    ("table_name", "columns"),
    [
        ("students", ["student_id"]),
        ("trainers", ["trainer_id"]),
        # `qualifications.qualification_code` is unique only where present —
        # asserted separately below, since a partial index is a different shape.
        ("units", ["unit_code"]),
        ("campuses", ["campus_code"]),
        ("colleges", ["college_short_name"]),
        # `course_offerings.course_code` is deliberately NOT unique: one CRICOS
        # code is offered at many campuses. See the test below.
        # Step 5B: unique per offering and intake, so "Group 1" can exist for
        # more than one qualification and intake at the same time.
        ("student_groups", ["course_offering_id", "intake", "group_code"]),
        ("timetable_plans", ["plan_reference"]),
        ("import_batches", ["batch_reference"]),
        ("users", ["organisation_email"]),
        ("users", ["entra_object_id"]),
        # COL-04
        ("course_offerings", ["college_id", "campus_id", "qualification_id"]),
        ("qualification_units", ["qualification_id", "unit_id"]),
        ("qualification_units", ["qualification_id", "delivery_order"]),
        ("offering_duration_options", ["course_offering_id", "duration_weeks"]),
        ("facilities", ["campus_id", "facility_reference"]),
        ("trainer_qualifications", ["trainer_id", "qualification_id"]),
        ("trainer_units", ["trainer_id", "unit_id"]),
        ("timetable_unit_deliveries", ["timetable_plan_id", "unit_id"]),
        ("import_staged_rows", ["import_batch_id", "source_row_number"]),
    ],
)
def test_approved_unique_constraint_exists(engine, table_name, columns):
    insp = inspect(engine)
    uniques = [set(u["column_names"]) for u in insp.get_unique_constraints(table_name, schema="public")]
    # A UNIQUE declared inline on a column may surface as a unique index.
    uniques += [
        set(i["column_names"])
        for i in insp.get_indexes(table_name, schema="public")
        if i.get("unique") and i.get("column_names")
    ]
    assert set(columns) in uniques, f"{table_name}: no UNIQUE on {columns}; found {uniques}"


def test_course_code_is_indexed_but_not_unique(engine):
    """A CRICOS code identifies the course, not its delivery at one campus.

    The real Page 4A export repeats 163 of 183 Course Codes across campuses, so a
    UNIQUE here would make the approved data unloadable. Offering identity is the
    composite COL-04 constraint, asserted above.
    """
    insp = inspect(engine)
    indexes = insp.get_indexes("course_offerings", schema="public")
    on_code = [i for i in indexes if i.get("column_names") == ["course_code"]]

    assert on_code, "course_code should stay indexed for lookup"
    assert not any(i.get("unique") for i in on_code), "course_code must not be unique"

    uniques = [set(u["column_names"]) for u in insp.get_unique_constraints("course_offerings", schema="public")]
    assert {"course_code"} not in uniques


def test_qualification_code_is_unique_only_where_present(engine):
    """ELICOS courses have no VET Code.

    Several code-less qualifications must coexist, while two qualifications must
    still never share a real code — that code is the business key students,
    trainers and timetables resolve against. A partial unique index expresses
    exactly that; a plain UNIQUE would reject the second code-less row and
    dropping uniqueness altogether would permit a genuine collision.
    """
    with engine.connect() as conn:
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'qualifications' AND column_name = 'qualification_code'"
            )
        ).scalar_one()
        predicate = conn.execute(
            text(
                "SELECT pg_get_expr(i.indpred, i.indrelid) FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'uq_qualifications_qualification_code'"
            )
        ).scalar_one()
        unique = conn.execute(
            text(
                "SELECT i.indisunique FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'uq_qualifications_qualification_code'"
            )
        ).scalar_one()

    assert nullable == "YES"
    assert unique is True
    assert predicate is not None and "not null" in predicate.lower()


def test_qualification_unit_order_constraint_is_deferrable(engine):
    """A whole reorder must be applicable inside one transaction."""
    with engine.connect() as conn:
        deferrable = conn.execute(
            text(
                "SELECT condeferrable FROM pg_constraint "
                "WHERE conname = 'uq_qualification_units_qualification_id_delivery_order'"
            )
        ).scalar_one()
    assert deferrable is True


def test_course_offering_has_composite_fk_to_college_campuses(engine):
    """COL-01 enforced by the database: an unapproved college/campus pair cannot be offered."""
    fks = inspect(engine).get_foreign_keys("course_offerings", schema="public")
    composite = [
        fk
        for fk in fks
        if fk["referred_table"] == "college_campuses"
        and set(fk["constrained_columns"]) == {"college_id", "campus_id"}
    ]
    assert composite, "missing composite FK to college_campuses"


def test_actual_course_duration_is_a_generated_column(engine):
    """DBQ-01: derived by one approved rule, so it cannot drift from the dates."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT is_generated, generation_expression FROM information_schema.columns "
                "WHERE table_name = 'students' AND column_name = 'actual_course_duration_weeks'"
            )
        ).one()
    assert row.is_generated == "ALWAYS"
    assert "7.0" in row.generation_expression


def test_no_duplicate_indexes(engine):
    """An index covering exactly the same columns as a unique constraint is redundant."""
    insp = inspect(engine)
    duplicates: list[str] = []
    for table in EXPECTED_TABLES:
        seen: dict[tuple[str, ...], str] = {}
        for idx in insp.get_indexes(table, schema="public"):
            cols = tuple(idx.get("column_names") or ())
            if not cols:
                continue
            key = cols
            if key in seen:
                duplicates.append(f"{table}: {idx['name']} duplicates {seen[key]}")
            else:
                seen[key] = idx["name"]
    assert not duplicates, "duplicate indexes: " + "; ".join(duplicates)


# ---------------------------------------------------------------------------
# Structural integrity — every insert is rolled back
# ---------------------------------------------------------------------------


def _minimal_reference_rows(conn) -> dict[str, int]:
    """Create the smallest reference chain needed to test student constraints."""
    college_id = conn.execute(
        text(
            "INSERT INTO colleges (college_short_name, college_full_name, is_active) "
            "VALUES ('T_CO', 'Test College', true) RETURNING id"
        )
    ).scalar_one()
    campus_id = conn.execute(
        text(
            "INSERT INTO campuses (campus_code, campus_name, campus_location, state, is_active) "
            "VALUES ('T_CA', 'Test Campus', 'Somewhere', 'TAS', true) RETURNING id"
        )
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO college_campuses (college_id, campus_id, is_active) "
            "VALUES (:c, :p, true)"
        ),
        {"c": college_id, "p": campus_id},
    )
    qualification_id = conn.execute(
        text(
            "INSERT INTO qualifications (qualification_code, qualification_title, is_active) "
            "VALUES ('T_QUAL', 'Test Qualification', true) RETURNING id"
        )
    ).scalar_one()
    status_id = conn.execute(
        text(
            "INSERT INTO course_statuses (code, label, selectable_for_new_records, is_active) "
            "VALUES ('T_ACTIVE', 'Active', true, true) RETURNING id"
        )
    ).scalar_one()
    offering_id = conn.execute(
        text(
            "INSERT INTO course_offerings "
            "(college_id, campus_id, qualification_id, course_code, course_status_id, is_deleted) "
            "VALUES (:c, :p, :q, 'T_COURSE', :s, false) RETURNING id"
        ),
        {"c": college_id, "p": campus_id, "q": qualification_id, "s": status_id},
    ).scalar_one()
    return {
        "college_id": college_id,
        "campus_id": campus_id,
        "qualification_id": qualification_id,
        "offering_id": offering_id,
    }


def _insert_student(conn, ids: dict[str, int], student_id: str, **overrides):
    params = {
        "sid": student_id,
        "off": ids["offering_id"],
        "start": "2026-01-05",
        "end": "2027-01-04",
    }
    params.update(overrides)
    return conn.execute(
        text(
            "INSERT INTO students (student_id, course_offering_id, college_email, first_name, "
            "coe_status, proposed_start_date, proposed_end_date, ct_student, is_deleted) "
            "VALUES (:sid, :off, 'x@example.com', 'Test', 'COE', :start, :end, false, false) "
            "RETURNING id"
        ),
        params,
    ).scalar_one()


def test_duplicate_student_id_is_rejected(connection):
    """DATA-01 / SST-05 enforced by PostgreSQL, not only by the frontend."""
    from sqlalchemy.exc import IntegrityError

    ids = _minimal_reference_rows(connection)
    _insert_student(connection, ids, "T_STU_1")
    with pytest.raises(IntegrityError):
        _insert_student(connection, ids, "T_STU_1")


def test_student_end_date_must_follow_start_date(connection):
    from sqlalchemy.exc import IntegrityError

    ids = _minimal_reference_rows(connection)
    with pytest.raises(IntegrityError):
        _insert_student(connection, ids, "T_STU_2", start="2027-01-04", end="2026-01-05")


def test_generated_duration_uses_inclusive_calculation(connection):
    """DBQ-01: (end - start + 1) / 7, rounded. 2026-01-05 to 2026-01-11 is 1 week."""
    ids = _minimal_reference_rows(connection)
    new_id = _insert_student(
        connection, ids, "T_STU_3", start="2026-01-05", end="2026-01-11"
    )
    weeks = connection.execute(
        text("SELECT actual_course_duration_weeks FROM students WHERE id = :i"), {"i": new_id}
    ).scalar_one()
    assert weeks == 1


def test_invalid_foreign_key_is_rejected(connection):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO students (student_id, course_offering_id, college_email, first_name, "
                "coe_status, proposed_start_date, proposed_end_date, ct_student, is_deleted) "
                "VALUES ('T_STU_4', 999999999, 'x@example.com', 'Test', 'COE', "
                "'2026-01-05', '2027-01-04', false, false)"
            )
        )


def test_unapproved_college_campus_pair_cannot_be_offered(connection):
    """COL-01: the composite FK rejects a college/campus combination never approved."""
    from sqlalchemy.exc import IntegrityError

    ids = _minimal_reference_rows(connection)
    other_campus = connection.execute(
        text(
            "INSERT INTO campuses (campus_code, campus_name, campus_location, state, is_active) "
            "VALUES ('T_CA2', 'Other', 'Elsewhere', 'VIC', true) RETURNING id"
        )
    ).scalar_one()
    status_id = connection.execute(
        text("SELECT id FROM course_statuses WHERE code = 'T_ACTIVE'")
    ).scalar_one()
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO course_offerings "
                "(college_id, campus_id, qualification_id, course_code, course_status_id, is_deleted) "
                "VALUES (:c, :p, :q, 'T_COURSE_2', :s, false)"
            ),
            {
                "c": ids["college_id"],
                "p": other_campus,
                "q": ids["qualification_id"],
                "s": status_id,
            },
        )


def test_the_work_assignment_column_is_gone(connection):
    """Access Model v1.1 removed the Data Editor work assignment entirely.

    A Data Editor now maintains both Student Data and Timetable, so the column
    decided nothing. Writing to it must fail because it no longer exists — not
    merely be ignored.
    """
    from sqlalchemy.exc import ProgrammingError

    with pytest.raises(ProgrammingError):
        connection.execute(
            text(
                "INSERT INTO users (organisation_email, display_name, access_level, "
                "data_editor_assignment, account_status) "
                "VALUES ('t@example.com', 'T', 'ADMIN', 'TIMETABLE_OFFICER', 'ACTIVE')"
            )
        )


def test_viewer_is_an_accepted_access_level(connection):
    """Access Model v1.1 added the fourth level."""
    connection.execute(
        text(
            "INSERT INTO users (organisation_email, display_name, access_level, account_status) "
            "VALUES ('viewer.test@example.com', 'T', 'VIEWER', 'ACTIVE')"
        )
    )
    assert connection.execute(
        text("SELECT access_level FROM users WHERE organisation_email = 'viewer.test@example.com'")
    ).scalar_one() == "VIEWER"


def test_organisation_email_is_case_insensitive(connection):
    """citext: two casings of one address must not become two accounts (AUTH-04)."""
    from sqlalchemy.exc import IntegrityError

    connection.execute(
        text(
            "INSERT INTO users (organisation_email, display_name, access_level, account_status) "
            "VALUES ('Case.Test@example.com', 'T', 'ADMIN', 'ACTIVE')"
        )
    )
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO users (organisation_email, display_name, access_level, account_status) "
                "VALUES ('case.test@EXAMPLE.com', 'T2', 'ADMIN', 'ACTIVE')"
            )
        )


def test_soft_delete_requires_complete_metadata(connection):
    """DATA-04 stated in SQL: no soft delete without who, when, why and the deadline."""
    from sqlalchemy.exc import IntegrityError

    ids = _minimal_reference_rows(connection)
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO students (student_id, course_offering_id, college_email, first_name, "
                "coe_status, proposed_start_date, proposed_end_date, ct_student, is_deleted) "
                "VALUES ('T_STU_5', :off, 'x@example.com', 'T', 'COE', "
                "'2026-01-05', '2027-01-04', false, true)"
            ),
            {"off": ids["offering_id"]},
        )


def test_additional_session_must_be_virtual(connection):
    """DBQ-14: MSCRIS is virtual only."""
    from sqlalchemy.exc import IntegrityError

    ids = _minimal_reference_rows(connection)
    group_id = connection.execute(
        text(
            "INSERT INTO student_groups (group_code, course_offering_id, intake, is_active) "
            "VALUES ('Group 1', :off, DATE '2026-01-01', true) RETURNING id"
        ),
        {"off": ids["offering_id"]},
    ).scalar_one()
    plan_id = connection.execute(
        text(
            "INSERT INTO timetable_plans (plan_reference, student_group_id, course_offering_id, "
            "duration_weeks, is_deleted) VALUES ('T_PLAN', :g, :off, 52, false) RETURNING id"
        ),
        {"g": group_id, "off": ids["offering_id"]},
    ).scalar_one()
    unit_id = connection.execute(
        text(
            "INSERT INTO units (unit_code, unit_title, is_active) "
            "VALUES ('T_UNIT', 'Test Unit', true) RETURNING id"
        )
    ).scalar_one()
    delivery_id = connection.execute(
        text(
            "INSERT INTO timetable_unit_deliveries (timetable_plan_id, unit_id, mode_of_delivery, "
            "start_date, end_date, is_deleted) "
            "VALUES (:p, :u, 'PHYSICAL', '2026-01-05', '2026-02-05', false) RETURNING id"
        ),
        {"p": plan_id, "u": unit_id},
    ).scalar_one()

    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO timetable_sessions (timetable_unit_delivery_id, session_type, weekday, "
                "start_time, end_time, delivery_mode, is_deleted) "
                "VALUES (:d, 'ADDITIONAL', 'MONDAY', '09:00', '11:00', 'PHYSICAL', false)"
            ),
            {"d": delivery_id},
        )


def test_session_end_time_must_follow_start_time(connection):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO timetable_sessions (timetable_unit_delivery_id, session_type, weekday, "
                "start_time, end_time, delivery_mode, is_deleted) "
                "VALUES (1, 'THEORY', 'MONDAY', '13:00', '09:00', 'PHYSICAL', false)"
            )
        )


def test_free_text_trainer_rejected_on_theory_session(connection):
    """DBQ-14: theory and practical cannot bypass approved trainer data (DATA-02)."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO timetable_sessions (timetable_unit_delivery_id, session_type, weekday, "
                "start_time, end_time, delivery_mode, trainer_name_text, is_deleted) "
                "VALUES (1, 'THEORY', 'MONDAY', '09:00', '11:00', 'PHYSICAL', 'Someone', false)"
            )
        )


def test_duplicate_trainer_qualification_is_rejected(connection):
    from sqlalchemy.exc import IntegrityError

    trainer_id = connection.execute(
        text(
            "INSERT INTO trainers (trainer_id, trainer_name, is_active, is_deleted) "
            "VALUES ('T_TRN', 'Test Trainer', true, false) RETURNING id"
        )
    ).scalar_one()
    qual_id = connection.execute(
        text(
            "INSERT INTO qualifications (qualification_code, qualification_title, is_active) "
            "VALUES ('T_QUAL_2', 'Q2', true) RETURNING id"
        )
    ).scalar_one()
    connection.execute(
        text("INSERT INTO trainer_qualifications (trainer_id, qualification_id) VALUES (:t, :q)"),
        {"t": trainer_id, "q": qual_id},
    )
    with pytest.raises(IntegrityError):
        connection.execute(
            text("INSERT INTO trainer_qualifications (trainer_id, qualification_id) VALUES (:t, :q)"),
            {"t": trainer_id, "q": qual_id},
        )


def test_activity_record_requires_an_outcome(connection):
    """LOG-02: an operational result, or the Microsoft/TDMS pair, must be present."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO user_activity_records (occurred_at, user_reference_snapshot, "
                "page_or_function, action, plain_language_detail) "
                "VALUES (now(), 'Unmatched user', 'Login and Authentication', 'SIGN_IN', 'x')"
            )
        )


def test_trainer_availability_view_unpivots_weekdays(connection):
    """The view turns five weekday columns into five rows per availability block."""
    ids = _minimal_reference_rows(connection)
    trainer_id = connection.execute(
        text(
            "INSERT INTO trainers (trainer_id, trainer_name, is_active, is_deleted) "
            "VALUES ('T_TRN_2', 'View Trainer', true, false) RETURNING id"
        )
    ).scalar_one()
    availability_id = connection.execute(
        text(
            "INSERT INTO trainer_availability (trainer_id, campus_id, class_type, "
            "working_time_start, working_time_end, monday, tuesday, wednesday, thursday, friday) "
            "VALUES (:t, :c, 'THEORY', '09:00', '17:00', 'PHYSICAL', 'VIRTUAL', "
            "'NOT_AVAILABLE', 'PHYSICAL', 'PHYSICAL') RETURNING id"
        ),
        {"t": trainer_id, "c": ids["campus_id"]},
    ).scalar_one()

    rows = connection.execute(
        text(
            "SELECT weekday, mode_of_delivery FROM trainer_availability_days "
            "WHERE availability_id = :a ORDER BY weekday"
        ),
        {"a": availability_id},
    ).fetchall()
    assert len(rows) == 5
    modes = dict(rows)
    assert modes["MONDAY"] == "PHYSICAL"
    assert modes["TUESDAY"] == "VIRTUAL"
    assert modes["WEDNESDAY"] == "NOT_AVAILABLE"
