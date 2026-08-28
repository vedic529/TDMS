"""Replace unused Schema v1 allocation tables with partitioned allocation records.

Revision ID: b7e4a91c2d80
Revises: a8c2e19f4b70
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7e4a91c2d80"
down_revision = "a8c2e19f4b70"
branch_labels = None
depends_on = None

PACKAGES = ("CHC", "BSB", "FNS", "SIT", "AUR", "CPC", "ICT", "RII", "TLI", "UEE", "AHC")


def upgrade() -> None:
    op.drop_table("timetable_clash_overrides")
    op.drop_index(
        "ix_timetable_sessions_trainer_id_weekday",
        table_name="timetable_sessions",
        postgresql_where=sa.text("trainer_id IS NOT NULL"),
    )
    op.drop_index("ix_timetable_sessions_timetable_unit_delivery_id", table_name="timetable_sessions")
    op.drop_index(
        "ix_timetable_sessions_facility_id_weekday",
        table_name="timetable_sessions",
        postgresql_where=sa.text("facility_id IS NOT NULL"),
    )
    op.drop_table("timetable_sessions")
    op.drop_index("ix_timetable_unit_deliveries_start_date_end_date", table_name="timetable_unit_deliveries")
    op.drop_table("timetable_unit_deliveries")
    op.drop_table("timetable_plans")
    postgresql.ENUM(name="session_type").drop(op.get_bind(), checkfirst=True)

    bind = op.get_bind()
    enums = {
        "uoc_type_allocation": ("THEORY_ONLY", "PRACTICAL_ONLY", "THEORY_AND_PRACTICAL"),
        "allocation_mode_of_delivery": ("F2FP", "F2FPV", "F2FV"),
        "allocation_stream": ("THEORY", "PRACTICAL", "MSCRIS"),
        "allocation_weekday": ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"),
        "session_delivery_mode": ("PHYSICAL", "VIRTUAL"),
        "virtual_classroom_kind": ("FACE_TO_FACE_VC", "FACE_TO_FACE_VIRTUAL"),
        "intake_match_status": ("MATCHED", "NOT_FOUND"),
        "suggestion_entity_type": ("COLLEGE", "CAMPUS", "QUALIFICATION", "UNIT", "FACILITY", "TRAINER"),
        "suggestion_status": ("PENDING", "ADDED", "MAPPED", "DELETED"),
        "suggestion_source": ("ALLOCATION_IMPORT", "ROLLING_IMPORT", "MANUAL"),
        "apply_mode": ("REPLACE", "MERGE"),
    }
    for name, values in enums.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "allocation_package_profile",
        sa.Column("training_package", postgresql.ENUM(name="training_package", create_type=False), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("training_package", name="pk_allocation_package_profile"),
    )
    for package in PACKAGES:
        enabled = "true" if package == "BSB" else "false"
        op.execute(
            f"INSERT INTO allocation_package_profile (training_package, enabled) "
            f"VALUES ('{package}'::training_package, {enabled})"
        )

    op.execute(
        """
        CREATE TABLE allocation_delivery (
            id bigint GENERATED ALWAYS AS IDENTITY,
            training_package training_package NOT NULL,
            college_id bigint NOT NULL,
            campus_id bigint NOT NULL,
            qualification_id bigint NOT NULL,
            duration_weeks integer NOT NULL,
            group_code text NOT NULL,
            unit_id bigint NOT NULL,
            uoc_type uoc_type_allocation NOT NULL,
            mode_of_delivery allocation_mode_of_delivery NOT NULL,
            start_date date NOT NULL,
            end_date date NOT NULL,
            classroom_size integer,
            remarks text,
            intake_match_status intake_match_status NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id, training_package),
            CONSTRAINT uq_allocation_delivery_business_key UNIQUE (
                training_package, college_id, campus_id, qualification_id,
                duration_weeks, unit_id, start_date, end_date
            ),
            CONSTRAINT ck_allocation_delivery_delivery_dates_ordered CHECK (end_date >= start_date),
            CONSTRAINT ck_allocation_delivery_allocation_duration_positive CHECK (duration_weeks > 0),
            CONSTRAINT fk_allocation_delivery_college_id_colleges
                FOREIGN KEY (college_id) REFERENCES colleges (id) ON DELETE RESTRICT,
            CONSTRAINT fk_allocation_delivery_campus_id_campuses
                FOREIGN KEY (campus_id) REFERENCES campuses (id) ON DELETE RESTRICT,
            CONSTRAINT fk_allocation_delivery_qualification_id_qualifications
                FOREIGN KEY (qualification_id) REFERENCES qualifications (id) ON DELETE RESTRICT,
            CONSTRAINT fk_allocation_delivery_unit_id_units
                FOREIGN KEY (unit_id) REFERENCES units (id) ON DELETE RESTRICT
        ) PARTITION BY LIST (training_package)
        """
    )
    for package in PACKAGES:
        op.execute(
            f'CREATE TABLE allocation_delivery_{package.lower()} '
            f"PARTITION OF allocation_delivery FOR VALUES IN ('{package}')"
        )

    op.execute(
        """
        CREATE TABLE allocation_delivery_intake (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            delivery_id bigint NOT NULL,
            training_package training_package NOT NULL,
            intake_label text NOT NULL,
            group_code text NOT NULL,
            CONSTRAINT uq_allocation_delivery_intake UNIQUE (delivery_id, training_package, intake_label),
            CONSTRAINT fk_allocation_delivery_intake_delivery
                FOREIGN KEY (delivery_id, training_package)
                REFERENCES allocation_delivery (id, training_package) ON DELETE CASCADE
        )
        """
    )
    op.create_index("ix_allocation_delivery_intake_intake_label", "allocation_delivery_intake", ["intake_label"])

    op.execute(
        """
        CREATE TABLE allocation_session (
            id bigint GENERATED ALWAYS AS IDENTITY,
            training_package training_package NOT NULL,
            delivery_id bigint NOT NULL,
            stream allocation_stream NOT NULL,
            weekday allocation_weekday NOT NULL,
            start_time time NOT NULL,
            end_time time NOT NULL,
            delivery_mode session_delivery_mode NOT NULL,
            facility_id bigint,
            virtual_kind virtual_classroom_kind,
            classroom_text text,
            trainer_id bigint,
            trainer_text text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id, training_package),
            CONSTRAINT uq_allocation_session_delivery_stream_weekday UNIQUE (
                training_package, delivery_id, stream, weekday
            ),
            CONSTRAINT ck_allocation_session_session_times_ordered CHECK (end_time > start_time),
            CONSTRAINT ck_allocation_session_virtual_has_no_facility CHECK (
                delivery_mode <> 'VIRTUAL' OR facility_id IS NULL
            ),
            CONSTRAINT ck_allocation_session_practical_is_physical CHECK (
                stream <> 'PRACTICAL' OR delivery_mode = 'PHYSICAL'
            ),
            CONSTRAINT ck_allocation_session_mscris_saturday_virtual CHECK (
                stream <> 'MSCRIS' OR (weekday = 'SATURDAY' AND delivery_mode = 'VIRTUAL')
            ),
            CONSTRAINT ck_allocation_session_non_mscris_not_saturday CHECK (
                stream = 'MSCRIS' OR weekday <> 'SATURDAY'
            ),
            CONSTRAINT fk_allocation_session_delivery
                FOREIGN KEY (delivery_id, training_package)
                REFERENCES allocation_delivery (id, training_package) ON DELETE CASCADE,
            CONSTRAINT fk_allocation_session_facility_id_facilities
                FOREIGN KEY (facility_id) REFERENCES facilities (id) ON DELETE RESTRICT,
            CONSTRAINT fk_allocation_session_trainer_id_trainers
                FOREIGN KEY (trainer_id) REFERENCES trainers (id) ON DELETE RESTRICT
        ) PARTITION BY LIST (training_package)
        """
    )
    for package in PACKAGES:
        op.execute(
            f'CREATE TABLE allocation_session_{package.lower()} '
            f"PARTITION OF allocation_session FOR VALUES IN ('{package}')"
        )
    op.execute(
        "CREATE INDEX ix_allocation_session_package_weekday "
        "ON allocation_session (training_package, weekday)"
    )
    op.execute(
        "CREATE INDEX ix_allocation_session_facility_weekday "
        "ON allocation_session (facility_id, weekday) WHERE facility_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_allocation_session_trainer_weekday "
        "ON allocation_session (trainer_id, weekday) WHERE trainer_id IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_allocation_session_delivery_id ON allocation_session (delivery_id)")

    op.create_table(
        "allocation_import_batch",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("training_package", postgresql.ENUM(name="training_package", create_type=False), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("apply_mode", postgresql.ENUM(name="apply_mode", create_type=False), nullable=False),
        sa.Column("rows_read", sa.Integer(), nullable=False),
        sa.Column("deliveries_written", sa.Integer(), nullable=False),
        sa.Column("sessions_written", sa.Integer(), nullable=False),
        sa.Column("deliveries_removed", sa.Integer(), nullable=False),
        sa.Column("suggestions_raised", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], name="fk_allocation_import_batch_uploaded_by_user_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_allocation_import_batch"),
    )

    op.execute(
        """
        CREATE TABLE allocation_source_row (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            batch_id bigint NOT NULL,
            training_package training_package,
            source_row_number integer NOT NULL,
            raw_values jsonb NOT NULL,
            delivery_id bigint,
            CONSTRAINT fk_allocation_source_row_batch_id_allocation_import_batch
                FOREIGN KEY (batch_id) REFERENCES allocation_import_batch (id) ON DELETE CASCADE,
            CONSTRAINT fk_allocation_source_row_delivery
                FOREIGN KEY (delivery_id, training_package)
                REFERENCES allocation_delivery (id, training_package) ON DELETE SET NULL
        )
        """
    )
    op.create_index("ix_allocation_source_row_batch_id", "allocation_source_row", ["batch_id"])

    op.create_table(
        "reference_suggestion",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("entity_type", postgresql.ENUM(name="suggestion_entity_type", create_type=False), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source", postgresql.ENUM(name="suggestion_source", create_type=False), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", postgresql.ENUM(name="suggestion_status", create_type=False), nullable=False, server_default="PENDING"),
        sa.Column("resolved_entity_id", sa.BigInteger(), nullable=True),
        sa.Column("resolved_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"], ["users.id"], name="fk_reference_suggestion_resolved_by_user_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reference_suggestion"),
        sa.UniqueConstraint(
            "entity_type", "raw_value", "context", name="uq_reference_suggestion_entity_raw_context"
        ),
    )
    op.create_index(
        "ix_reference_suggestion_status_entity", "reference_suggestion", ["status", "entity_type"]
    )


def downgrade() -> None:
    raise RuntimeError("Allocation records replace unused Schema v1 tables; downgrade is not supported.")
