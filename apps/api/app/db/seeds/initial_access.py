"""Report the elevated bootstrap list and its binding status.

    python -m app.db.seeds.initial_access --status

**This command no longer writes anything.** Under Access Model v1.1, TDMS
accounts are created at the first verified Microsoft sign-in, which is also where
the display name comes from — Entra profile claims rather than a guess at
someone's name. Step 4's `--apply` mode has been removed because there is nothing
left for it to insert; `--dry-run` is kept as an alias so the documented command
still works.

What it is for now: checking, before or after a rollout, that the controlled
access values exist, that each approved elevated address is bound to exactly the
role it should be, and that nothing has drifted.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.seeds.manifest import (
    DEFAULT_ACCESS_LEVEL,
    ELEVATED_BOOTSTRAP,
    EXPECTED_COUNTS,
    INITIAL_ACCOUNT_STATUS,
    BootstrapUser,
    validate_manifest,
)
from app.db.session import DatabaseNotConfiguredError, get_session_factory
from app.models.user import User

# The controlled access values the schema must offer. These are PostgreSQL enum
# types, so there is nothing to INSERT for them — only to verify. Seeding them
# into a parallel lookup table would create two competing definitions of who may
# do what.
REQUIRED_ENUM_VALUES: dict[str, set[str]] = {
    "access_level": {"VIEWER", "DATA_EDITOR", "ADMIN", "SUPER_ADMIN"},
    "account_status": {"ACTIVE", "INACTIVE", "DISABLED"},
    "access_request_status": {"PENDING", "APPROVED", "DENIED", "CANCELLED"},
}

# Table names that would indicate a second, competing access model had appeared
# alongside the approved enums.
FORBIDDEN_PARALLEL_TABLES = ("access_levels", "roles", "user_roles", "data_editor_assignments")


class Outcome(str, Enum):
    """The binding state of one approved elevated address."""

    AWAITING_FIRST_SIGN_IN = "AWAITING_FIRST_SIGN_IN"
    BOUND = "BOUND"
    PROVISIONED_NOT_YET_LINKED = "PROVISIONED_NOT_YET_LINKED"
    ROLE_DIFFERS = "ROLE_DIFFERS"
    NOT_ACTIVE = "NOT_ACTIVE"

    @property
    def is_problem(self) -> bool:
        return self in {Outcome.ROLE_DIFFERS, Outcome.NOT_ACTIVE}


@dataclass
class PlannedUser:
    user: BootstrapUser
    outcome: Outcome
    detail: str = ""


@dataclass
class SeedPlan:
    planned: list[PlannedUser] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def of(self, *outcomes: Outcome) -> list[PlannedUser]:
        return [p for p in self.planned if p.outcome in outcomes]

    @property
    def flagged(self) -> list[PlannedUser]:
        return [p for p in self.planned if p.outcome.is_problem]

    @property
    def healthy(self) -> bool:
        return not self.problems and not self.flagged


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------


def check_controlled_values(session: Session) -> list[str]:
    """Verify the approved access values exist, as enum types."""
    problems: list[str] = []

    rows = session.execute(
        text(
            """
            SELECT t.typname, e.enumlabel
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public' AND t.typname = ANY(:names)
            """
        ),
        {"names": list(REQUIRED_ENUM_VALUES)},
    ).all()

    actual: dict[str, set[str]] = {}
    for typname, label in rows:
        actual.setdefault(typname, set()).add(label)

    for name, expected in REQUIRED_ENUM_VALUES.items():
        found = actual.get(name)
        if found is None:
            problems.append(f"enum type {name!r} does not exist")
        elif found != expected:
            missing = sorted(expected - found)
            extra = sorted(found - expected)
            problems.append(
                f"enum {name!r} mismatch — missing {missing or 'none'}, unexpected {extra or 'none'}"
            )

    # Access Model v1.1 removed the Data Editor work assignment entirely.
    if session.execute(
        text("SELECT count(*) FROM pg_type WHERE typname = 'data_editor_assignment'")
    ).scalar_one():
        problems.append("obsolete enum type 'data_editor_assignment' still exists")

    present = {
        row[0]
        for row in session.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = ANY(:names)"
            ),
            {"names": list(FORBIDDEN_PARALLEL_TABLES)},
        ).all()
    }
    if present:
        problems.append(
            f"a second access model exists alongside the approved enums: {sorted(present)}"
        )

    return problems


def check_no_domain_accounts(session: Session) -> list[str]:
    """No row may stand for a whole domain — a domain grants nothing."""
    rows = session.execute(
        select(User.organisation_email).where(
            text("organisation_email LIKE '@%' OR organisation_email LIKE '%*%'")
        )
    ).all()
    return [f"domain/wildcard account row present: {row[0]!r}" for row in rows]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def build_plan(session: Session, users: tuple[BootstrapUser, ...] = ELEVATED_BOOTSTRAP) -> SeedPlan:
    """Report the binding state of every approved elevated address."""
    plan = SeedPlan()
    plan.problems.extend(validate_manifest(users))
    plan.problems.extend(check_controlled_values(session))
    plan.problems.extend(check_no_domain_accounts(session))

    emails = [u.organisation_email for u in users]
    found = (
        session.execute(select(User).where(User.organisation_email.in_(emails))).scalars().all()
        if emails
        else []
    )
    existing = {row.organisation_email.lower(): row for row in found}

    for user in users:
        row = existing.get(user.organisation_email.lower())

        if row is None:
            plan.planned.append(
                PlannedUser(
                    user,
                    Outcome.AWAITING_FIRST_SIGN_IN,
                    "created at first verified Microsoft sign-in",
                )
            )
            continue

        if row.access_level != user.access_level:
            plan.planned.append(
                PlannedUser(
                    user,
                    Outcome.ROLE_DIFFERS,
                    f"approved {user.access_level}, actual {row.access_level}",
                )
            )
            continue

        if row.account_status != INITIAL_ACCOUNT_STATUS:
            plan.planned.append(
                PlannedUser(user, Outcome.NOT_ACTIVE, f"status {row.account_status}")
            )
            continue

        if row.entra_object_id is None:
            plan.planned.append(
                PlannedUser(user, Outcome.PROVISIONED_NOT_YET_LINKED, "no Microsoft identity bound")
            )
        else:
            plan.planned.append(PlannedUser(user, Outcome.BOUND, "Microsoft identity bound"))

    return plan


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_SYMBOL = {
    Outcome.AWAITING_FIRST_SIGN_IN: ".",
    Outcome.BOUND: "=",
    Outcome.PROVISIONED_NOT_YET_LINKED: "~",
    Outcome.ROLE_DIFFERS: "!",
    Outcome.NOT_ACTIVE: "!",
}


def render(plan: SeedPlan) -> str:
    """Human-readable status.

    ASCII only: this is printed to a Windows console, where the default code page
    turns an em dash into a replacement character. Contains no credential and no
    connection string.
    """
    settings = get_settings()
    lines = [
        "TDMS elevated bootstrap status (read-only)",
        f"target   : {settings.safe_database_target}",
        "",
    ]

    width = max((len(p.user.organisation_email) for p in plan.planned), default=0)
    for p in plan.planned:
        detail = f"  ({p.detail})" if p.detail else ""
        lines.append(
            f"  {_SYMBOL[p.outcome]} {p.user.organisation_email:<{width}}  "
            f"{p.user.access_level:<12} {p.outcome.value}{detail}"
        )

    counts = {level: 0 for level in EXPECTED_COUNTS}
    for p in plan.planned:
        counts[p.user.access_level] = counts.get(p.user.access_level, 0) + 1

    lines += [
        "",
        f"approved : {len(plan.planned)} elevated accounts - "
        + ", ".join(f"{level} {counts.get(level, 0)}" for level in ("ADMIN", "SUPER_ADMIN")),
        f"bound    : {len(plan.of(Outcome.BOUND))}",
        f"awaiting : {len(plan.of(Outcome.AWAITING_FIRST_SIGN_IN, Outcome.PROVISIONED_NOT_YET_LINKED))}",
        f"flagged  : {len(plan.flagged)}",
        "",
        f"Every other approved-tenant user is provisioned as {DEFAULT_ACCESS_LEVEL} on first sign-in.",
        "This command writes nothing: accounts are created by verified sign-in.",
    ]

    if plan.flagged:
        lines += ["", "FLAGGED - differs from the approved bootstrap list:"]
        lines += [
            f"  ! {p.user.organisation_email}: {p.outcome.value} - {p.detail}" for p in plan.flagged
        ]
        lines += [
            "",
            "Not repaired automatically. A role is changed by a Super Admin in the",
            "administration dashboard, which records the change in the activity records.",
        ]

    if plan.problems:
        lines += ["", "STRUCTURAL PROBLEMS:"]
        lines += [f"  ! {problem}" for problem in plan.problems]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.db.seeds.initial_access",
        description=(
            "Report the elevated bootstrap list and its binding status. "
            "Read-only: accounts are created at first verified Microsoft sign-in."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="report bootstrap binding status")
    group.add_argument(
        "--dry-run", action="store_true", help="alias for --status (kept for continuity)"
    )
    parser.parse_args(argv)

    try:
        factory = get_session_factory()
    except DatabaseNotConfiguredError as exc:
        print(f"database not configured: {exc}", file=sys.stderr)
        return 2

    with factory() as session:
        try:
            plan = build_plan(session)
        except Exception as exc:  # pragma: no cover - connection failures
            print(f"could not inspect the database: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

        print(render(plan))
        return 0 if plan.healthy else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
