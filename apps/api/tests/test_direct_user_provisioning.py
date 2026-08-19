"""Direct user provisioning: a Super Admin grants access without a request.

This is deliberately *not* the access-request workflow. Nobody asked; a Super
Admin decided. The two must stay separate, or the table that answers "who asked
for what?" fills with decisions nobody requested.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.access_request import AccessRequest
from app.models.activity import UserActivityRecord
from app.models.user import User

from tests.test_reference_data_api import (  # noqa: F401
    ADMIN,
    EDITOR as DATA_EDITOR,
    SUPER as SUPER_ADMIN,
    VIEWER,
    as_user,
    client,
    people,
)

NEW_EMAIL = "new.person@chelsongordon.com"


def add_user(client, email: str, level: str, *, actor=SUPER_ADMIN):
    return client.post(
        "/admin/users",
        json={"organisation_email": email, "access_level": level},
        headers=as_user(actor),
    )


class TestSuperAdminMayProvisionEveryLevel:
    @pytest.mark.parametrize("level", ["VIEWER", "DATA_EDITOR", "ADMIN", "SUPER_ADMIN"])
    def test_each_access_level_can_be_granted_directly(self, client, people, level):
        response = add_user(client, f"{level.lower()}.person@chelsongordon.com", level)
        assert response.status_code == 201, response.text

        body = response.json()
        assert body["access_level"] == level
        assert body["account_status"] == "ACTIVE"
        assert body["identity_linked"] is False
        assert body["display_name"] is None


class TestOnlySuperAdmin:
    @pytest.mark.parametrize("actor", [ADMIN, DATA_EDITOR, VIEWER])
    def test_every_lower_role_is_refused(self, client, people, actor):
        """Authorisation is the endpoint's, not the button's."""
        assert add_user(client, NEW_EMAIL, "VIEWER", actor=actor).status_code == 403

    def test_an_unauthenticated_caller_is_refused(self, client, people):
        response = client.post(
            "/admin/users",
            json={"organisation_email": NEW_EMAIL, "access_level": "VIEWER"},
        )
        assert response.status_code == 401


class TestValidation:
    @pytest.mark.parametrize("email", ["", "   ", "not-an-email", "@nodomain", "user@", "a b@c.com"])
    def test_an_invalid_email_is_refused(self, client, people, email):
        assert add_user(client, email, "VIEWER").status_code == 422

    def test_an_unknown_access_level_is_refused(self, client, people):
        response = add_user(client, NEW_EMAIL, "SUPERVISOR")
        assert response.status_code in (400, 422)

    def test_surrounding_whitespace_is_trimmed(self, client, people):
        response = add_user(client, f"  {NEW_EMAIL}  ", "VIEWER")
        assert response.status_code == 201
        assert response.json()["organisation_email"] == NEW_EMAIL


class TestExistingAccounts:
    def test_the_same_email_in_another_case_is_not_a_second_account(self, client, people):
        """`organisation_email` is citext, so this is caught in SQL, not by luck."""
        assert add_user(client, NEW_EMAIL, "VIEWER").status_code == 201

        clash = add_user(client, NEW_EMAIL.upper(), "VIEWER")
        assert clash.status_code == 409
        assert "already exists" in clash.json()["detail"]

    def test_an_existing_user_with_the_same_role_is_reported_not_duplicated(
        self, client, people, session
    ):
        add_user(client, NEW_EMAIL, "DATA_EDITOR")
        response = add_user(client, NEW_EMAIL, "DATA_EDITOR")

        assert response.status_code == 409
        assert "already exists with Data Editor access" in response.json()["detail"]
        assert session.execute(
            select(User).where(User.organisation_email == NEW_EMAIL)
        ).scalars().all().__len__() == 1

    def test_an_existing_user_with_a_different_role_is_sent_to_change_role(
        self, client, people, session
    ):
        """Add User never silently overwrites an access level."""
        add_user(client, NEW_EMAIL, "VIEWER")
        response = add_user(client, NEW_EMAIL, "ADMIN")

        assert response.status_code == 409
        assert "Use Change role" in response.json()["detail"]

        unchanged = session.execute(
            select(User).where(User.organisation_email == NEW_EMAIL)
        ).scalar_one()
        assert unchanged.access_level == "VIEWER"

    def test_a_disabled_account_is_not_silently_reactivated(self, client, people, session):
        """Deactivation is a decision; Add User must not undo it by accident."""
        add_user(client, NEW_EMAIL, "VIEWER")
        target = session.execute(
            select(User).where(User.organisation_email == NEW_EMAIL)
        ).scalar_one()
        target.account_status = "DISABLED"
        session.commit()

        response = add_user(client, NEW_EMAIL, "VIEWER")
        assert response.status_code == 409
        assert "disabled" in response.json()["detail"].lower()

        session.refresh(target)
        assert target.account_status == "DISABLED"

    def test_a_super_admin_cannot_provision_their_own_email(self, client, people):
        """The existing self-change protection is not bypassable through Add User."""
        response = add_user(client, SUPER_ADMIN, "VIEWER")
        assert response.status_code == 403
        assert "your own access level" in response.json()["detail"]


class TestMicrosoftIdentity:
    def test_a_new_account_is_created_unlinked(self, client, people, session):
        add_user(client, NEW_EMAIL, "ADMIN")

        created = session.execute(
            select(User).where(User.organisation_email == NEW_EMAIL)
        ).scalar_one()
        assert created.entra_object_id is None
        assert created.entra_tenant_id is None

    def test_no_name_is_derived_from_the_mailbox(self, client, people, session):
        """`john.smith@` must not become "John Smith"."""
        add_user(client, "john.smith@chelsongordon.com", "VIEWER")

        created = session.execute(
            select(User).where(User.organisation_email == "john.smith@chelsongordon.com")
        ).scalar_one()
        assert created.display_name is None

    def test_first_sign_in_links_the_identity_and_keeps_the_granted_role(
        self, client, people, session
    ):
        """The pre-provisioned role survives; the JIT Viewer default does not apply."""
        from app.auth.claims import VerifiedClaims
        from app.auth.identity import resolve_user

        add_user(client, NEW_EMAIL, "ADMIN")

        oid, tid = uuid.uuid4(), uuid.uuid4()
        claims = VerifiedClaims(
            tenant_id=tid,
            object_id=oid,
            username=NEW_EMAIL,
            display_name="Verified Person",
            token_reference="test",
        )
        user = resolve_user(session, claims)
        session.commit()

        assert user.access_level == "ADMIN", "a granted role must not be reset to Viewer"
        assert user.entra_object_id == oid
        assert user.entra_tenant_id == tid
        assert user.display_name == "Verified Person"

    def test_a_pre_provisioned_super_admin_stays_super_admin(self, client, people, session):
        from app.auth.claims import VerifiedClaims
        from app.auth.identity import resolve_user

        add_user(client, NEW_EMAIL, "SUPER_ADMIN")
        user = resolve_user(
            session,
            VerifiedClaims(
                tenant_id=uuid.uuid4(),
                object_id=uuid.uuid4(),
                username=NEW_EMAIL,
                display_name="Verified Person",
                token_reference="test",
            ),
        )
        session.commit()
        assert user.access_level == "SUPER_ADMIN"


class TestAudit:
    def test_an_activity_record_is_written(self, client, people, session):
        add_user(client, NEW_EMAIL, "ADMIN")

        record = session.execute(
            select(UserActivityRecord)
            .where(UserActivityRecord.action == "USER_PROVISIONED")
            .order_by(UserActivityRecord.id.desc())
        ).scalars().first()

        assert record is not None
        assert record.record_reference == NEW_EMAIL
        assert record.access_level_snapshot == "SUPER_ADMIN"
        assert "Admin" in record.plain_language_detail
        assert record.page_or_function == "Administration - User & Role Management"

    def test_no_access_request_row_is_created(self, client, people, session):
        """Nobody requested this. The request table records questions, not decrees."""
        before = session.execute(select(AccessRequest)).scalars().all()
        add_user(client, NEW_EMAIL, "ADMIN")
        after = session.execute(select(AccessRequest)).scalars().all()
        assert len(after) == len(before)

    def test_a_refused_addition_writes_no_account_and_no_audit(
        self, client, people, session
    ):
        add_user(client, NEW_EMAIL, "VIEWER")
        provisioned = session.execute(
            select(UserActivityRecord).where(
                UserActivityRecord.action == "USER_PROVISIONED"
            )
        ).scalars().all()

        add_user(client, NEW_EMAIL, "ADMIN")  # refused
        still = session.execute(
            select(UserActivityRecord).where(
                UserActivityRecord.action == "USER_PROVISIONED"
            )
        ).scalars().all()
        assert len(still) == len(provisioned)


class TestLastSuperAdminProtection:
    def test_adding_another_super_admin_is_allowed(self, client, people):
        assert add_user(client, NEW_EMAIL, "SUPER_ADMIN").status_code == 201

    def test_the_existing_demotion_safeguard_is_untouched(self, client, people, session):
        """Provisioning must not become a way around the last-Super-Admin rule."""
        super_admins = session.execute(
            select(User).where(
                User.access_level == "SUPER_ADMIN", User.account_status == "ACTIVE"
            )
        ).scalars().all()
        assert len(super_admins) >= 1
