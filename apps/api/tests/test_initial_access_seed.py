"""The elevated bootstrap list and its status command (Access Model v1.1).

Step 4's seed *inserted* six accounts and was blocked on missing display names.
Access Model v1.1 supersedes that: the list declares email -> role, and accounts
are created at the first verified Microsoft sign-in, where the display name comes
from Entra rather than from a guess. These tests cover what remains — that the
list is exactly what was approved, and that the status command reports the truth
without writing anything.

Provisioning itself is tested in `test_access_model_v11.py`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.seeds import initial_access
from app.db.seeds.initial_access import (
    Outcome,
    build_plan,
    check_controlled_values,
    check_no_domain_accounts,
    render,
)
from app.db.seeds.manifest import (
    APPROVAL_NOTIFICATION_RECIPIENTS,
    ELEVATED_BOOTSTRAP,
    EXPECTED_COUNTS,
    NOTIFICATION_SENDER,
    BootstrapUser,
    bootstrap_role_for,
    validate_manifest,
)
from app.models.user import User

pytestmark = pytest.mark.database

API_DIR = Path(__file__).resolve().parents[1]

SUPER_ADMINS = {
    "a.chattopadhyay@chelsongordon.com",
    "w.rajjak@chelsongordon.com",
    "v.yadav@chelsongordon.com",
    "d.panda@chelsongordon.com",
}
ADMINS = {"c.dejsakultorn@chelsongordon.com", "n.verma@chelsongordon.com"}


# ---------------------------------------------------------------------------
# The approved list
# ---------------------------------------------------------------------------


def test_list_is_internally_valid():
    assert validate_manifest() == []


def test_four_super_admins_and_two_admins():
    counts = {level: 0 for level in EXPECTED_COUNTS}
    for user in ELEVATED_BOOTSTRAP:
        counts[user.access_level] += 1
    assert counts == {"VIEWER": 0, "DATA_EDITOR": 0, "ADMIN": 2, "SUPER_ADMIN": 4}


def test_exact_super_admin_addresses():
    assert {u.organisation_email for u in ELEVATED_BOOTSTRAP if u.access_level == "SUPER_ADMIN"} == (
        SUPER_ADMINS
    )


def test_exact_admin_addresses():
    assert {u.organisation_email for u in ELEVATED_BOOTSTRAP if u.access_level == "ADMIN"} == ADMINS


def test_n_verma_is_admin_not_super_admin():
    """Access Model v1.1 §5 moved this account down from Super Admin."""
    assert bootstrap_role_for("n.verma@chelsongordon.com") == "ADMIN"
    assert "n.verma@chelsongordon.com" not in SUPER_ADMINS


def test_no_data_editor_or_viewer_is_bootstrapped():
    for user in ELEVATED_BOOTSTRAP:
        assert user.access_level in {"ADMIN", "SUPER_ADMIN"}


def test_bootstrap_lookup_is_case_insensitive():
    assert bootstrap_role_for("A.Chattopadhyay@ChelsonGordon.com") == "SUPER_ADMIN"
    assert bootstrap_role_for("  n.verma@chelsongordon.com  ") == "ADMIN"


def test_unknown_address_has_no_bootstrap_role():
    assert bootstrap_role_for("someone.else@chelsongordon.com") is None
    assert bootstrap_role_for("") is None


def test_a_domain_is_not_a_bootstrap_entry():
    assert bootstrap_role_for("@chelsongordon.com") is None
    assert bootstrap_role_for("@vconsultancy.com.au") is None


def test_list_rejects_a_domain_entry():
    bad = (BootstrapUser("@chelsongordon.com", "ADMIN"),)
    assert any("domain or wildcard" in p for p in validate_manifest(bad))


def test_list_rejects_an_uppercase_address():
    bad = (BootstrapUser("A.Person@Chelsongordon.com", "ADMIN"),)
    assert any("lowercase" in p for p in validate_manifest(bad))


def test_list_rejects_viewer_as_a_bootstrap_role():
    bad = (BootstrapUser("someone@chelsongordon.com", "VIEWER"),)
    assert any("VIEWER is the default" in p for p in validate_manifest(bad))


def test_list_holds_no_demo_or_mock_account():
    forbidden = ("example.com", "example.org", "test@", "demo@", "localhost")
    for user in ELEVATED_BOOTSTRAP:
        assert not any(f in user.organisation_email for f in forbidden)


def test_list_carries_no_password_or_secret_field():
    for user in ELEVATED_BOOTSTRAP:
        keys = set(vars(user))
        assert not {"password", "password_hash", "secret", "token", "pin"} & keys


# ---------------------------------------------------------------------------
# Notification routing (§50, §51)
# ---------------------------------------------------------------------------


def test_approval_notifications_go_to_the_four_super_admins():
    assert set(APPROVAL_NOTIFICATION_RECIPIENTS) == SUPER_ADMINS


def test_n_verma_does_not_receive_approval_notifications():
    assert "n.verma@chelsongordon.com" not in APPROVAL_NOTIFICATION_RECIPIENTS


def test_notification_sender_is_the_approved_mailbox():
    assert NOTIFICATION_SENDER == "v.yadav@chelsongordon.com"


# ---------------------------------------------------------------------------
# Controlled access values
# ---------------------------------------------------------------------------


def test_controlled_access_values_exist_as_enums(session):
    assert check_controlled_values(session) == []


def test_access_level_enum_has_exactly_four_values_in_privilege_order(session):
    labels = session.execute(
        text(
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'access_level' ORDER BY e.enumsortorder"
        )
    ).scalars().all()
    assert labels == ["VIEWER", "DATA_EDITOR", "ADMIN", "SUPER_ADMIN"]


def test_postgresql_orders_access_levels_by_privilege(session):
    assert session.execute(text("SELECT 'VIEWER'::access_level < 'DATA_EDITOR'::access_level")).scalar_one()
    assert session.execute(text("SELECT 'ADMIN'::access_level < 'SUPER_ADMIN'::access_level")).scalar_one()


def test_data_editor_assignment_type_is_gone(session):
    assert session.execute(
        text("SELECT count(*) FROM pg_type WHERE typname = 'data_editor_assignment'")
    ).scalar_one() == 0


def test_users_table_has_no_assignment_column(session):
    columns = session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
    ).scalars().all()
    assert "data_editor_assignment" not in columns


def test_activity_records_have_no_assignment_snapshot(session):
    columns = session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'user_activity_records'"
        )
    ).scalars().all()
    assert "assignment_snapshot" not in columns


def test_no_parallel_lookup_table_shadows_the_enums(session):
    names = session.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(:n)"
        ),
        {"n": list(initial_access.FORBIDDEN_PARALLEL_TABLES)},
    ).scalars().all()
    assert names == []


def test_users_table_has_no_password_column(session):
    columns = session.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
    ).scalars().all()
    joined = " ".join(columns).lower()
    for word in ("password", "passwd", "secret", "hash", "token", "pin"):
        assert word not in joined


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


def test_status_on_an_empty_database_reports_all_awaiting_sign_in(session):
    plan = build_plan(session)
    assert len(plan.of(Outcome.AWAITING_FIRST_SIGN_IN)) == 6
    assert plan.healthy


def test_status_writes_nothing(session):
    build_plan(session)
    session.rollback()
    assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


def test_status_reports_a_bound_account(session):
    import uuid

    session.add(
        User(
            organisation_email="d.panda@chelsongordon.com",
            display_name="Supplied By Microsoft",
            access_level="SUPER_ADMIN",
            account_status="ACTIVE",
            entra_object_id=uuid.uuid4(),
            entra_tenant_id=uuid.uuid4(),
        )
    )
    session.commit()
    plan = build_plan(session)
    assert len(plan.of(Outcome.BOUND)) == 1
    assert plan.healthy


def test_status_flags_a_role_that_differs_from_the_approved_list(session):
    session.add(
        User(
            organisation_email="n.verma@chelsongordon.com",
            display_name="Supplied By Microsoft",
            access_level="SUPER_ADMIN",  # approved list says ADMIN
            account_status="ACTIVE",
        )
    )
    session.commit()
    plan = build_plan(session)
    flagged = plan.of(Outcome.ROLE_DIFFERS)
    assert len(flagged) == 1
    assert "approved ADMIN, actual SUPER_ADMIN" in flagged[0].detail
    assert not plan.healthy


def test_status_does_not_repair_a_flagged_role(session):
    session.add(
        User(
            organisation_email="n.verma@chelsongordon.com",
            display_name="Supplied By Microsoft",
            access_level="SUPER_ADMIN",
            account_status="ACTIVE",
        )
    )
    session.commit()
    build_plan(session)
    session.commit()
    row = session.execute(
        select(User).where(User.organisation_email == "n.verma@chelsongordon.com")
    ).scalar_one()
    assert row.access_level == "SUPER_ADMIN"


def test_status_flags_a_disabled_bootstrap_account(session):
    session.add(
        User(
            organisation_email="w.rajjak@chelsongordon.com",
            display_name="Supplied By Microsoft",
            access_level="SUPER_ADMIN",
            account_status="DISABLED",
        )
    )
    session.commit()
    plan = build_plan(session)
    assert len(plan.of(Outcome.NOT_ACTIVE)) == 1
    assert not plan.healthy


def test_no_domain_account_row_exists(session):
    assert check_no_domain_accounts(session) == []


def test_render_never_exposes_a_credential(session):
    output = render(build_plan(session))
    settings = get_settings()
    assert settings.database_url not in output
    assert "://" not in output
    if "@" in settings.database_url:
        secret = settings.database_url.split("://", 1)[1].split("@", 1)[0]
        assert secret not in output


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _clean_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}


def test_cli_status_reports_and_writes_nothing(test_database_url, session):
    result = subprocess.run(
        [sys.executable, "-m", "app.db.seeds.initial_access", "--status"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        env={**_clean_env(), "DATABASE_URL": test_database_url},
    )
    assert result.returncode == 0, result.stderr
    assert "AWAITING_FIRST_SIGN_IN" in result.stdout
    assert "writes nothing" in result.stdout
    assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


def test_cli_has_no_apply_mode(test_database_url):
    """Step 4's --apply is gone: accounts are created by verified sign-in."""
    result = subprocess.run(
        [sys.executable, "-m", "app.db.seeds.initial_access", "--apply"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        env={**_clean_env(), "DATABASE_URL": test_database_url},
    )
    assert result.returncode != 0


def test_cli_requires_an_explicit_mode(test_database_url):
    result = subprocess.run(
        [sys.executable, "-m", "app.db.seeds.initial_access"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
        env={**_clean_env(), "DATABASE_URL": test_database_url},
    )
    assert result.returncode != 0
