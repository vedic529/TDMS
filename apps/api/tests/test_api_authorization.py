"""Endpoint-level authorisation, exercised over HTTP.

These call the API directly rather than checking whether a button is hidden.
Hiding a control is a courtesy to the user; the only thing that actually stops a
Viewer from approving their own promotion is the server refusing the request.

Development (`mock`) authentication is used so the tests need no real Microsoft
tenant. What is under test is the authorisation layer, which is identical either
way — `get_current_user` produces the same `User` from either source.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import deps
from app.auth.mock import mock_claims_for
from app.core.config import Settings, get_settings
from app.db.seeds.manifest import bootstrap_role_for
from app.main import app
from app.models.user import User
from app.services import access_requests as service

pytestmark = pytest.mark.database

VIEWER = "viewer@chelsongordon.com"
EDITOR = "editor@chelsongordon.com"
ADMIN = "admin@chelsongordon.com"
SUPER = "a.chattopadhyay@chelsongordon.com"
SUPER_2 = "w.rajjak@chelsongordon.com"


@pytest.fixture()
def client(test_factory, test_engine, session):
    """A TestClient bound to the temporary database and mock authentication."""

    def _get_db():
        db = test_factory()
        try:
            yield db
        finally:
            db.close()

    # Pinned explicitly rather than inherited from the ambient environment: if a
    # developer sets TDMS_AUTH_MODE=entra in their .env, these tests must still
    # exercise the authorisation layer rather than start failing on tokens.
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="development", auth_mode="mock"
    )
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def as_user(client: TestClient, email: str):
    """Headers naming the development user for this call."""
    return {deps.MOCK_USER_HEADER: email}


def seed_people(session):
    """Create the four levels. Super Admins arrive through the bootstrap list."""
    for email, level in ((VIEWER, "VIEWER"), (EDITOR, "DATA_EDITOR"), (ADMIN, "ADMIN")):
        claims = mock_claims_for(email)
        session.add(
            User(
                organisation_email=email,
                display_name=f"Test {email}",
                access_level=level,
                account_status="ACTIVE",
                entra_object_id=claims.object_id,
                entra_tenant_id=claims.tenant_id,
            )
        )
    for email in (SUPER, SUPER_2):
        claims = mock_claims_for(email)
        session.add(
            User(
                organisation_email=email,
                display_name=f"Test {email}",
                access_level=bootstrap_role_for(email),
                account_status="ACTIVE",
                entra_object_id=claims.object_id,
                entra_tenant_id=claims.tenant_id,
            )
        )
    session.commit()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_health_needs_no_authentication(client):
    assert client.get("/health").status_code == 200


def test_me_requires_authentication(client):
    response = client.get("/me")
    assert response.status_code == 401


def test_administration_requires_authentication(client):
    assert client.get("/admin/overview").status_code == 401
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/access-requests").status_code == 401


def test_first_sign_in_provisions_a_viewer(client, session):
    response = client.get("/me", headers=as_user(client, "brand.new@chelsongordon.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["access_level"] == "VIEWER"
    assert body["user"]["account_status"] == "ACTIVE"
    assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 1


def test_me_returns_the_authoritative_capability_map(client, session):
    seed_people(session)
    body = client.get("/me", headers=as_user(client, VIEWER)).json()
    assert body["capabilities"]["view"] is True
    assert body["capabilities"]["maintainStudentData"] is False
    assert body["requestable_roles"] == ["DATA_EDITOR", "ADMIN", "SUPER_ADMIN"]
    assert body["session_inactivity_minutes"] == 30


def test_a_disabled_account_is_refused(client, session):
    seed_people(session)
    user = session.execute(
        text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
    ).scalar_one()
    session.execute(
        text("UPDATE users SET account_status = 'DISABLED' WHERE id = :i"), {"i": user}
    )
    session.commit()
    assert client.get("/me", headers=as_user(client, VIEWER)).status_code == 403


# ---------------------------------------------------------------------------
# Direct API calls, per level
# ---------------------------------------------------------------------------


class TestViewer:
    def test_may_read_their_own_identity(self, client, session):
        seed_people(session)
        assert client.get("/me", headers=as_user(client, VIEWER)).status_code == 200

    def test_may_not_reach_administration(self, client, session):
        seed_people(session)
        for path in ("/admin/overview", "/admin/users", "/admin/access-requests",
                     "/admin/activity-records"):
            assert client.get(path, headers=as_user(client, VIEWER)).status_code == 403, path

    def test_may_not_change_anybody_s_role(self, client, session):
        seed_people(session)
        target = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": EDITOR}
        ).scalar_one()
        response = client.post(
            f"/admin/users/{target}/role",
            json={"access_level": "SUPER_ADMIN"},
            headers=as_user(client, VIEWER),
        )
        assert response.status_code == 403

    def test_may_not_approve_a_request(self, client, session):
        seed_people(session)
        viewer = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
        ).scalar_one()
        user = session.get(User, viewer)
        request = service.submit_request(session, user, "ADMIN")
        session.commit()

        response = client.post(
            f"/admin/access-requests/{request.id}/approve", headers=as_user(client, VIEWER)
        )
        assert response.status_code == 403
        session.expire_all()
        assert session.get(User, viewer).access_level == "VIEWER"


class TestDataEditor:
    def test_maintains_students_and_timetable(self, client, session):
        seed_people(session)
        caps = client.get("/me", headers=as_user(client, EDITOR)).json()["capabilities"]
        assert caps["maintainStudentData"] is True
        assert caps["maintainTimetable"] is True

    def test_cannot_maintain_reference_data(self, client, session):
        seed_people(session)
        caps = client.get("/me", headers=as_user(client, EDITOR)).json()["capabilities"]
        assert caps["maintainTrainerData"] is False
        assert caps["maintainReferenceData"] is False

    def test_may_not_reach_administration(self, client, session):
        seed_people(session)
        assert client.get("/admin/overview", headers=as_user(client, EDITOR)).status_code == 403


class TestAdmin:
    def test_may_maintain_reference_data(self, client, session):
        seed_people(session)
        caps = client.get("/me", headers=as_user(client, ADMIN)).json()["capabilities"]
        assert caps["maintainTrainerData"] is True
        assert caps["maintainReferenceData"] is True

    def test_may_not_decide_an_access_request(self, client, session):
        """Access Model v1.1 §5: approving requests is Super Admin work."""
        seed_people(session)
        viewer = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
        ).scalar_one()
        request = service.submit_request(session, session.get(User, viewer), "DATA_EDITOR")
        session.commit()

        approve = client.post(
            f"/admin/access-requests/{request.id}/approve", headers=as_user(client, ADMIN)
        )
        deny = client.post(
            f"/admin/access-requests/{request.id}/deny", headers=as_user(client, ADMIN)
        )
        assert approve.status_code == 403
        assert deny.status_code == 403

        session.expire_all()
        assert session.get(User, viewer).access_level == "VIEWER"

    def test_may_not_assign_admin_or_super_admin(self, client, session):
        seed_people(session)
        target = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
        ).scalar_one()
        for role in ("ADMIN", "SUPER_ADMIN"):
            response = client.post(
                f"/admin/users/{target}/role",
                json={"access_level": role},
                headers=as_user(client, ADMIN),
            )
            assert response.status_code == 403, role

    def test_may_not_list_users_or_activity_records(self, client, session):
        seed_people(session)
        assert client.get("/admin/users", headers=as_user(client, ADMIN)).status_code == 403
        assert (
            client.get("/admin/activity-records", headers=as_user(client, ADMIN)).status_code == 403
        )


class TestSuperAdmin:
    def test_may_reach_every_administration_area(self, client, session):
        seed_people(session)
        for path in ("/admin/overview", "/admin/users", "/admin/access-requests",
                     "/admin/activity-records"):
            assert client.get(path, headers=as_user(client, SUPER)).status_code == 200, path

    def test_overview_counts_are_real(self, client, session):
        seed_people(session)
        body = client.get("/admin/overview", headers=as_user(client, SUPER)).json()
        assert body["viewer_count"] == 1
        assert body["data_editor_count"] == 1
        assert body["admin_count"] == 1
        assert body["super_admin_count"] == 2
        assert body["active_users"] == 5
        assert body["pending_access_requests"] == 0

    def test_may_approve_a_request(self, client, session):
        seed_people(session)
        viewer_id = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
        ).scalar_one()
        request = service.submit_request(session, session.get(User, viewer_id), "DATA_EDITOR")
        session.commit()

        response = client.post(
            f"/admin/access-requests/{request.id}/approve", headers=as_user(client, SUPER)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

        session.expire_all()
        assert session.get(User, viewer_id).access_level == "DATA_EDITOR"

    def test_a_second_decision_is_refused_over_http(self, client, session):
        seed_people(session)
        viewer_id = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
        ).scalar_one()
        request = service.submit_request(session, session.get(User, viewer_id), "ADMIN")
        session.commit()

        first = client.post(
            f"/admin/access-requests/{request.id}/approve", headers=as_user(client, SUPER)
        )
        second = client.post(
            f"/admin/access-requests/{request.id}/deny", headers=as_user(client, SUPER_2)
        )
        assert first.status_code == 200
        assert second.status_code == 409
        assert "already been decided" in second.json()["detail"]

    def test_may_not_decide_their_own_request_over_http(self, client, session):
        seed_people(session)
        # A Super Admin has nothing higher to request, so the row is built
        # directly to prove the endpoint refuses regardless of how it got there.
        from app.models.access_request import AccessRequest

        sa_id = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": SUPER}
        ).scalar_one()
        session.execute(
            text("UPDATE users SET access_level = 'ADMIN' WHERE id = :i"), {"i": sa_id}
        )
        request = AccessRequest(
            requester_user_id=sa_id, role_at_request="ADMIN", requested_role="SUPER_ADMIN"
        )
        session.add(request)
        session.commit()
        session.execute(
            text("UPDATE users SET access_level = 'SUPER_ADMIN' WHERE id = :i"), {"i": sa_id}
        )
        session.commit()

        response = client.post(
            f"/admin/access-requests/{request.id}/approve", headers=as_user(client, SUPER)
        )
        assert response.status_code == 403
        assert "your own" in response.json()["detail"].lower()

    def test_may_change_a_role(self, client, session):
        seed_people(session)
        target = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": VIEWER}
        ).scalar_one()
        response = client.post(
            f"/admin/users/{target}/role",
            json={"access_level": "ADMIN"},
            headers=as_user(client, SUPER),
        )
        assert response.status_code == 200
        assert response.json()["access_level"] == "ADMIN"

    def test_may_not_change_their_own_role(self, client, session):
        seed_people(session)
        sa_id = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": SUPER}
        ).scalar_one()
        response = client.post(
            f"/admin/users/{sa_id}/role",
            json={"access_level": "VIEWER"},
            headers=as_user(client, SUPER),
        )
        assert response.status_code == 403
        session.expire_all()
        assert session.get(User, sa_id).access_level == "SUPER_ADMIN"

    def test_cannot_remove_the_last_super_admin_over_http(self, client, session):
        seed_people(session)
        first = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": SUPER}
        ).scalar_one()
        second = session.execute(
            text("SELECT id FROM users WHERE organisation_email = :e"), {"e": SUPER_2}
        ).scalar_one()

        # Two exist: demoting one is allowed.
        assert (
            client.post(
                f"/admin/users/{second}/role",
                json={"access_level": "ADMIN"},
                headers=as_user(client, SUPER),
            ).status_code
            == 200
        )
        # One left, and they cannot demote themselves.
        assert (
            client.post(
                f"/admin/users/{first}/role",
                json={"access_level": "ADMIN"},
                headers=as_user(client, SUPER),
            ).status_code
            == 403
        )
        session.expire_all()
        assert session.get(User, first).access_level == "SUPER_ADMIN"


# ---------------------------------------------------------------------------
# The request workflow over HTTP
# ---------------------------------------------------------------------------


def test_submitting_a_request_reports_the_notification_truthfully(client, session):
    seed_people(session)
    response = client.post(
        "/me/access-requests", json={"requested_role": "DATA_EDITOR"}, headers=as_user(client, VIEWER)
    )
    assert response.status_code == 201
    notification = response.json()["notification"]
    # Graph is not configured, so the API must not claim an email was delivered.
    assert notification["delivered"] is False
    assert notification["provider"] == "development"


def test_a_second_pending_request_is_refused(client, session):
    seed_people(session)
    first = client.post(
        "/me/access-requests", json={"requested_role": "ADMIN"}, headers=as_user(client, VIEWER)
    )
    second = client.post(
        "/me/access-requests",
        json={"requested_role": "DATA_EDITOR"},
        headers=as_user(client, VIEWER),
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_requesting_a_lower_role_is_refused(client, session):
    seed_people(session)
    response = client.post(
        "/me/access-requests", json={"requested_role": "VIEWER"}, headers=as_user(client, ADMIN)
    )
    assert response.status_code == 422


def test_a_requester_may_cancel_over_http(client, session):
    seed_people(session)
    created = client.post(
        "/me/access-requests", json={"requested_role": "ADMIN"}, headers=as_user(client, VIEWER)
    ).json()["request"]
    response = client.delete(
        f"/me/access-requests/{created['id']}", headers=as_user(client, VIEWER)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_one_user_cannot_cancel_anothers_request(client, session):
    seed_people(session)
    created = client.post(
        "/me/access-requests", json={"requested_role": "ADMIN"}, headers=as_user(client, VIEWER)
    ).json()["request"]
    response = client.delete(f"/me/access-requests/{created['id']}", headers=as_user(client, EDITOR))
    assert response.status_code == 400


def test_activity_records_capture_the_workflow(client, session):
    seed_people(session)
    created = client.post(
        "/me/access-requests", json={"requested_role": "DATA_EDITOR"}, headers=as_user(client, VIEWER)
    ).json()["request"]
    client.post(f"/admin/access-requests/{created['id']}/approve", headers=as_user(client, SUPER))

    records = client.get("/admin/activity-records", headers=as_user(client, SUPER)).json()
    actions = {r["action"] for r in records}
    assert "ACCESS_REQUEST_SUBMITTED" in actions
    assert "ACCESS_REQUEST_APPROVED" in actions


def test_no_activity_record_carries_a_token_or_secret(client, session):
    seed_people(session)
    client.post(
        "/me/access-requests", json={"requested_role": "ADMIN"}, headers=as_user(client, VIEWER)
    )
    records = client.get("/admin/activity-records", headers=as_user(client, SUPER)).json()
    blob = " ".join(str(r) for r in records).lower()
    for forbidden in ("bearer ", "password", "client_secret", "refresh_token", "access_token"):
        assert forbidden not in blob


def test_auth_configuration_exposes_no_secret(client):
    body = client.get("/auth/configuration").json()
    assert "clientSecret" not in body
    assert "secret" not in " ".join(body.keys()).lower()
    assert body["authMode"] in {"mock", "entra"}
