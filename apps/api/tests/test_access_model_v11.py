"""Access Model v1.1 — authentication, authorisation and access requests.

The tests that matter most here are the ones that try to break the rules:
requesting a lower role, deciding your own request, two Super Admins racing on
one request, demoting the last Super Admin, and a Viewer calling a write endpoint
directly rather than looking for a hidden button.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth.claims import AuthenticationError, TenantNotAllowedError, VerifiedClaims
from app.auth.identity import (
    InactiveAccountError,
    count_active_super_admins,
    find_user_by_identity,
    resolve_user,
)
from app.auth.tokens import CONSUMER_TENANT_ID, claims_from_payload, verify_access_token
from app.core import rbac
from app.core.config import Settings
from app.models.access_request import AccessRequest
from app.models.user import User
from app.services import access_requests as service

pytestmark = pytest.mark.database

ALLOWED_TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT = uuid.UUID("22222222-2222-4222-8222-222222222222")

#: Test-only stand-ins. The real IDs live in the git-ignored environment files,
#: so the *shape* of validation is tested without pinning a tenant into Git.
API_CLIENT_ID = "00000000-0000-4000-8000-0000000000a1"
SPA_CLIENT_ID = "00000000-0000-4000-8000-0000000000b2"
OTHER_CLIENT_ID = "00000000-0000-4000-8000-0000000000c3"


def claims(
    email: str,
    *,
    tenant: uuid.UUID = ALLOWED_TENANT,
    oid: uuid.UUID | None = None,
    name: str | None = None,
) -> VerifiedClaims:
    return VerifiedClaims(
        tenant_id=tenant,
        object_id=oid or uuid.uuid5(uuid.NAMESPACE_URL, email),
        username=email,
        display_name=name or f"Name From Microsoft ({email})",
        token_reference="test",
    )


def make_user(session, email: str, level: str, *, status: str = "ACTIVE", linked: bool = True):
    user = User(
        organisation_email=email,
        display_name=f"Test {email}",
        access_level=level,
        account_status=status,
        entra_object_id=uuid.uuid5(uuid.NAMESPACE_URL, email) if linked else None,
        entra_tenant_id=ALLOWED_TENANT if linked else None,
    )
    session.add(user)
    session.flush()
    return user


# ===========================================================================
# The authorisation policy
# ===========================================================================


class TestPolicy:
    def test_four_levels_in_ascending_privilege(self):
        assert rbac.rank("VIEWER") < rbac.rank("DATA_EDITOR") < rbac.rank("ADMIN") < rbac.rank(
            "SUPER_ADMIN"
        )

    def test_viewer_may_view_and_export_only(self):
        caps = rbac.capabilities_for("VIEWER")
        assert caps["view"] and caps["export"]
        for denied in (
            "maintainStudentData",
            "maintainTimetable",
            "maintainTrainerData",
            "maintainReferenceData",
            "viewActivityRecords",
            "accessAdministration",
            "manageUserRoles",
            "decideAccessRequests",
        ):
            assert caps[denied] is False, denied

    def test_data_editor_maintains_both_students_and_timetable(self):
        """The work assignment that used to split these is gone."""
        caps = rbac.capabilities_for("DATA_EDITOR")
        assert caps["maintainStudentData"] is True
        assert caps["maintainTimetable"] is True

    def test_data_editor_cannot_maintain_reference_data(self):
        caps = rbac.capabilities_for("DATA_EDITOR")
        assert caps["maintainTrainerData"] is False
        assert caps["maintainReferenceData"] is False
        # …but may still look at and download it.
        assert caps["view"] and caps["export"]

    def test_admin_maintains_reference_data(self):
        caps = rbac.capabilities_for("ADMIN")
        assert caps["maintainTrainerData"] is True
        assert caps["maintainReferenceData"] is True

    def test_admin_cannot_decide_access_requests_or_manage_roles(self):
        caps = rbac.capabilities_for("ADMIN")
        assert caps["decideAccessRequests"] is False
        assert caps["manageUserRoles"] is False
        assert caps["accessAdministration"] is False

    def test_super_admin_holds_every_capability(self):
        caps = rbac.capabilities_for("SUPER_ADMIN")
        assert all(caps.values())

    def test_no_assignment_concept_remains_in_the_policy(self):
        joined = " ".join(rbac.capabilities_for("DATA_EDITOR"))
        assert "OFFICER" not in joined.upper()

    @pytest.mark.parametrize(
        "level,expected",
        [
            ("VIEWER", ("DATA_EDITOR", "ADMIN", "SUPER_ADMIN")),
            ("DATA_EDITOR", ("ADMIN", "SUPER_ADMIN")),
            ("ADMIN", ("SUPER_ADMIN",)),
            ("SUPER_ADMIN", ()),
        ],
    )
    def test_only_higher_roles_are_requestable(self, level, expected):
        assert rbac.requestable_roles_for(level) == expected

    def test_viewer_is_never_requestable(self):
        for level in ("VIEWER", "DATA_EDITOR", "ADMIN", "SUPER_ADMIN"):
            assert "VIEWER" not in rbac.requestable_roles_for(level)


# ===========================================================================
# Tenant admission — the real security boundary
# ===========================================================================


class TestTenantAllowList:
    def _settings(self, **overrides) -> Settings:
        """Settings pinned field by field.

        Every Entra field is set explicitly, including the ones that default to
        "off". `Settings` reads the real `.env` through its default factories, so
        omitting a field would make these tests pass or fail depending on how the
        developer's machine happens to be configured.
        """
        base = dict(
            auth_mode="entra",
            entra_client_id=API_CLIENT_ID,
            entra_allowed_tenant_ids=[str(ALLOWED_TENANT)],
            entra_authorized_client_ids=[],
            entra_api_scope="",
        )
        base.update(overrides)
        return Settings(**base)

    def _token(self, tenant: str) -> str:
        import jwt

        return jwt.encode({"tid": tenant, "oid": str(uuid.uuid4())}, "unused", algorithm="HS256")

    def test_unknown_tenant_is_denied(self):
        with pytest.raises(TenantNotAllowedError):
            verify_access_token(self._token(str(OTHER_TENANT)), self._settings())

    def test_personal_microsoft_account_tenant_is_denied(self):
        with pytest.raises(TenantNotAllowedError):
            verify_access_token(self._token(CONSUMER_TENANT_ID), self._settings())

    def test_consumer_tenant_is_denied_even_if_someone_allow_lists_it(self):
        """Organisation-only is a policy, not a configuration accident."""
        settings = self._settings(entra_allowed_tenant_ids=[CONSUMER_TENANT_ID])
        with pytest.raises(TenantNotAllowedError):
            verify_access_token(self._token(CONSUMER_TENANT_ID), settings)

    def test_correct_domain_in_the_wrong_tenant_is_denied(self):
        """Anyone can create a lookalike mailbox in a tenant they control."""
        import jwt

        token = jwt.encode(
            {
                "tid": str(OTHER_TENANT),
                "oid": str(uuid.uuid4()),
                "preferred_username": "a.chattopadhyay@chelsongordon.com",
            },
            "unused",
            algorithm="HS256",
        )
        with pytest.raises(TenantNotAllowedError):
            verify_access_token(token, self._settings())

    def test_token_without_a_tenant_claim_is_denied(self):
        import jwt

        token = jwt.encode({"oid": str(uuid.uuid4())}, "unused", algorithm="HS256")
        with pytest.raises(AuthenticationError):
            verify_access_token(token, self._settings())

    def test_unverified_jwt_is_never_accepted(self):
        """A token from an allowed tenant still has to be signed by it."""
        import jwt

        token = jwt.encode(
            {"tid": str(ALLOWED_TENANT), "oid": str(uuid.uuid4()), "aud": "wrong"},
            "attacker-key",
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            # Fails before any network call would succeed: HS256 is not allowed
            # and the signature cannot be verified against the tenant's JWKS.
            verify_access_token(token, self._settings())

    def test_garbage_is_rejected(self):
        with pytest.raises(AuthenticationError):
            verify_access_token("not-a-token", self._settings())

    def test_empty_token_is_rejected(self):
        with pytest.raises(AuthenticationError):
            verify_access_token("   ", self._settings())

    def test_unconfigured_entra_mode_refuses_rather_than_admitting(self):
        settings = self._settings(entra_client_id="", entra_allowed_tenant_ids=[])
        with pytest.raises(AuthenticationError):
            verify_access_token(self._token(str(ALLOWED_TENANT)), settings)

    def test_production_never_falls_back_to_mock(self):
        settings = Settings(app_env="production", auth_mode="mock")
        assert settings.auth_configuration_error() is not None

    def test_development_may_use_mock(self):
        settings = Settings(app_env="development", auth_mode="mock")
        assert settings.auth_configuration_error() is None

    def test_a_token_without_the_required_scope_is_rejected(self):
        """A token minted for another API in the same tenant must not be replayed."""
        from app.auth.tokens import _require_scope

        settings = self._settings(entra_api_scope="access_as_user")
        with pytest.raises(AuthenticationError):
            _require_scope({"scp": "User.Read"}, settings)
        with pytest.raises(AuthenticationError):
            _require_scope({}, settings)

    def test_a_token_carrying_the_required_scope_is_accepted(self):
        from app.auth.tokens import _require_scope

        settings = self._settings(entra_api_scope="access_as_user")
        _require_scope({"scp": "openid profile access_as_user"}, settings)

    def test_scope_is_not_enforced_until_one_is_configured(self):
        """The audience check still limits the token to this application."""
        from app.auth.tokens import _require_scope

        _require_scope({"scp": "anything"}, self._settings())

    def test_application_permissions_do_not_satisfy_a_delegated_scope(self):
        """`roles` carries app permissions; a user token must use `scp`."""
        from app.auth.tokens import _require_scope

        settings = self._settings(entra_api_scope="access_as_user")
        with pytest.raises(AuthenticationError):
            _require_scope({"roles": ["access_as_user"]}, settings)

    # -- v2 access-token claims ---------------------------------------------

    def _v2_claims(self, **overrides) -> dict:
        """A minimal, well-formed v2 access-token payload."""
        payload = {
            "ver": "2.0",
            "aud": API_CLIENT_ID,
            "tid": str(ALLOWED_TENANT),
            "oid": str(uuid.uuid4()),
            "azp": SPA_CLIENT_ID,
            "scp": "access_as_user",
            "preferred_username": "someone@chelsongordon.com",
            "name": "Someone",
        }
        payload.update(overrides)
        return payload

    def test_a_v1_token_is_rejected(self):
        """The API registration requests v2; v1 has different claim semantics."""
        from app.auth.tokens import _require_token_version

        with pytest.raises(AuthenticationError):
            _require_token_version(self._v2_claims(ver="1.0"))

    def test_a_token_with_no_version_claim_is_rejected(self):
        from app.auth.tokens import _require_token_version

        payload = self._v2_claims()
        del payload["ver"]
        with pytest.raises(AuthenticationError):
            _require_token_version(payload)

    def test_a_v2_token_version_is_accepted(self):
        from app.auth.tokens import _require_token_version

        _require_token_version(self._v2_claims())

    def test_a_token_from_an_unauthorised_client_is_rejected(self):
        """Audience and scope alone would admit any pre-authorised app."""
        from app.auth.tokens import _require_authorized_client

        settings = self._settings(entra_authorized_client_ids=[SPA_CLIENT_ID])
        with pytest.raises(AuthenticationError):
            _require_authorized_client(self._v2_claims(azp=OTHER_CLIENT_ID), settings)

    def test_a_token_from_the_authorised_client_is_accepted(self):
        from app.auth.tokens import _require_authorized_client

        settings = self._settings(entra_authorized_client_ids=[SPA_CLIENT_ID])
        _require_authorized_client(self._v2_claims(), settings)

    def test_the_authorised_client_check_accepts_the_v1_appid_spelling(self):
        from app.auth.tokens import _require_authorized_client

        settings = self._settings(entra_authorized_client_ids=[SPA_CLIENT_ID])
        payload = self._v2_claims()
        del payload["azp"]
        payload["appid"] = SPA_CLIENT_ID
        _require_authorized_client(payload, settings)

    def test_a_token_with_no_client_claim_is_rejected_when_pinned(self):
        from app.auth.tokens import _require_authorized_client

        settings = self._settings(entra_authorized_client_ids=[SPA_CLIENT_ID])
        payload = self._v2_claims()
        del payload["azp"]
        with pytest.raises(AuthenticationError):
            _require_authorized_client(payload, settings)

    def test_the_client_check_is_skipped_when_none_is_configured(self):
        from app.auth.tokens import _require_authorized_client

        _require_authorized_client(self._v2_claims(azp=OTHER_CLIENT_ID), self._settings())

    def test_the_expected_audience_is_the_api_client_id_not_the_uri(self):
        """For a v2 token `aud` is the client ID; `api://...` is how it is asked for."""
        settings = self._settings()
        assert settings.entra_client_id == API_CLIENT_ID
        assert not settings.entra_client_id.startswith("api://")

    def test_the_v2_issuer_pattern_is_tenant_specific(self):
        from app.auth.tokens import _issuer

        issuer = _issuer(str(ALLOWED_TENANT), self._settings())
        assert issuer == f"https://login.microsoftonline.com/{ALLOWED_TENANT}/v2.0"
        assert issuer.endswith("/v2.0")

    def test_the_jwks_url_is_the_tenant_v2_key_set(self):
        from app.auth.tokens import _jwks_url

        url = _jwks_url(str(ALLOWED_TENANT), self._settings())
        assert url == f"https://login.microsoftonline.com/{ALLOWED_TENANT}/discovery/v2.0/keys"

    def test_claims_require_a_username(self):
        with pytest.raises(AuthenticationError):
            claims_from_payload({"tid": str(ALLOWED_TENANT), "oid": str(uuid.uuid4())})

    def test_claims_reject_a_non_uuid_object_id(self):
        with pytest.raises(AuthenticationError):
            claims_from_payload(
                {"tid": str(ALLOWED_TENANT), "oid": "not-a-uuid", "preferred_username": "a@b.com"}
            )


# ===========================================================================
# Provisioning
# ===========================================================================


class TestProvisioning:
    def test_unknown_organisational_user_becomes_a_viewer(self, session):
        user = resolve_user(session, claims("new.person@chelsongordon.com"))
        session.commit()
        assert user.access_level == "VIEWER"
        assert user.account_status == "ACTIVE"
        assert user.entra_object_id is not None
        assert user.entra_tenant_id == ALLOWED_TENANT

    def test_a_domain_never_grants_more_than_viewer(self, session):
        for email in ("someone@chelsongordon.com", "someone@vconsultancy.com.au"):
            user = resolve_user(session, claims(email))
            session.commit()
            assert user.access_level == "VIEWER", email

    def test_display_name_comes_from_microsoft_not_from_the_mailbox(self, session):
        user = resolve_user(
            session, claims("j.smith@chelsongordon.com", name="Jane Smith")
        )
        session.commit()
        assert user.display_name == "Jane Smith"

    def test_second_sign_in_finds_the_same_user(self, session):
        first = resolve_user(session, claims("repeat@chelsongordon.com"))
        session.commit()
        second = resolve_user(session, claims("repeat@chelsongordon.com"))
        session.commit()
        assert first.id == second.id
        assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 1

    def test_no_password_is_ever_stored(self, session):
        resolve_user(session, claims("nopass@chelsongordon.com"))
        session.commit()
        columns = session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
        ).scalars().all()
        assert not [c for c in columns if "password" in c.lower() or "secret" in c.lower()]

    # -- elevated bootstrap binding -----------------------------------------

    @pytest.mark.parametrize(
        "email,expected",
        [
            ("a.chattopadhyay@chelsongordon.com", "SUPER_ADMIN"),
            ("w.rajjak@chelsongordon.com", "SUPER_ADMIN"),
            ("v.yadav@chelsongordon.com", "SUPER_ADMIN"),
            ("d.panda@chelsongordon.com", "SUPER_ADMIN"),
            ("c.dejsakultorn@chelsongordon.com", "ADMIN"),
            ("n.verma@chelsongordon.com", "ADMIN"),
        ],
    )
    def test_bootstrap_address_binds_at_its_approved_role(self, session, email, expected):
        user = resolve_user(session, claims(email))
        session.commit()
        assert user.access_level == expected
        assert user.entra_object_id is not None

    def test_bootstrap_binding_is_case_insensitive(self, session):
        user = resolve_user(session, claims("D.Panda@ChelsonGordon.com"))
        session.commit()
        assert user.access_level == "SUPER_ADMIN"
        assert user.organisation_email == "d.panda@chelsongordon.com"

    def test_role_is_not_recalculated_from_a_changed_mailbox(self, session):
        """The durable identity is tid + oid, so a rename changes nothing."""
        oid = uuid.uuid4()
        user = resolve_user(session, claims("d.panda@chelsongordon.com", oid=oid))
        session.commit()
        assert user.access_level == "SUPER_ADMIN"

        renamed = resolve_user(
            session, claims("divya.panda@chelsongordon.com", oid=oid, name="Divya Panda")
        )
        session.commit()

        assert renamed.id == user.id
        assert renamed.access_level == "SUPER_ADMIN"
        assert renamed.organisation_email == "divya.panda@chelsongordon.com"
        assert renamed.display_name == "Divya Panda"
        assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 1

    def test_a_demotion_is_not_undone_at_the_next_sign_in(self, session):
        """The bootstrap list is consulted once, not on every sign-in."""
        oid = uuid.uuid4()
        user = resolve_user(session, claims("v.yadav@chelsongordon.com", oid=oid))
        session.commit()
        assert user.access_level == "SUPER_ADMIN"

        user.access_level = "VIEWER"
        session.commit()

        again = resolve_user(session, claims("v.yadav@chelsongordon.com", oid=oid))
        session.commit()
        assert again.access_level == "VIEWER"

    def test_a_reused_mailbox_does_not_inherit_the_previous_holders_access(self, session):
        """Someone else's oid must never adopt an account already bound."""
        first = resolve_user(session, claims("w.rajjak@chelsongordon.com", oid=uuid.uuid4()))
        session.commit()
        assert first.access_level == "SUPER_ADMIN"

        # A different person, same mailbox text, different Microsoft identity.
        with pytest.raises(IntegrityError):
            resolve_user(session, claims("w.rajjak@chelsongordon.com", oid=uuid.uuid4()))
            session.flush()
        session.rollback()

    def test_pre_provisioned_unbound_account_is_adopted(self, session):
        make_user(session, "preprovisioned@chelsongordon.com", "ADMIN", linked=False)
        session.commit()

        user = resolve_user(session, claims("preprovisioned@chelsongordon.com"))
        session.commit()

        assert user.access_level == "ADMIN"
        assert user.entra_object_id is not None
        assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 1

    # -- account status ------------------------------------------------------

    @pytest.mark.parametrize("status", ["INACTIVE", "DISABLED"])
    def test_a_non_active_account_is_refused(self, session, status):
        make_user(session, "blocked@chelsongordon.com", "ADMIN", status=status)
        session.commit()
        with pytest.raises(InactiveAccountError):
            resolve_user(session, claims("blocked@chelsongordon.com"))

    def test_a_disabled_account_is_not_replaced_by_a_second_one(self, session):
        make_user(session, "blocked@chelsongordon.com", "ADMIN", status="DISABLED")
        session.commit()
        with pytest.raises(InactiveAccountError):
            resolve_user(session, claims("blocked@chelsongordon.com"))
        session.rollback()
        assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 1


# ===========================================================================
# Access requests
# ===========================================================================


class TestAccessRequests:
    def test_viewer_can_request_data_editor(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        request = service.submit_request(session, user, "DATA_EDITOR")
        session.commit()
        assert request.status == "PENDING"
        assert request.role_at_request == "VIEWER"
        assert request.requested_role == "DATA_EDITOR"

    def test_no_reason_is_required(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()
        assert request.decision_note is None

    @pytest.mark.parametrize("requested", ["VIEWER", "DATA_EDITOR"])
    def test_data_editor_cannot_request_its_own_or_a_lower_role(self, session, requested):
        user = make_user(session, "editor@chelsongordon.com", "DATA_EDITOR")
        with pytest.raises(service.InvalidRequestedRole):
            service.submit_request(session, user, requested)

    def test_super_admin_has_nothing_to_request(self, session):
        user = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        assert rbac.requestable_roles_for(user.access_level) == ()
        with pytest.raises(service.InvalidRequestedRole):
            service.submit_request(session, user, "SUPER_ADMIN")

    def test_only_one_pending_request_at_a_time(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        service.submit_request(session, user, "ADMIN")
        session.commit()
        with pytest.raises(service.RequestAlreadyPending):
            service.submit_request(session, user, "DATA_EDITOR")

    def test_the_database_itself_forbids_two_pending_requests(self, session):
        """Belt and braces: the partial unique index settles a genuine race."""
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        session.commit()
        session.add(
            AccessRequest(
                requester_user_id=user.id, role_at_request="VIEWER", requested_role="ADMIN"
            )
        )
        session.flush()
        session.add(
            AccessRequest(
                requester_user_id=user.id, role_at_request="VIEWER", requested_role="DATA_EDITOR"
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_the_database_forbids_requesting_a_lower_role(self, session):
        user = make_user(session, "admin@chelsongordon.com", "ADMIN")
        session.commit()
        session.add(
            AccessRequest(
                requester_user_id=user.id, role_at_request="ADMIN", requested_role="DATA_EDITOR"
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_the_database_forbids_requesting_viewer(self, session):
        user = make_user(session, "someone@chelsongordon.com", "VIEWER")
        session.commit()
        session.add(
            AccessRequest(
                requester_user_id=user.id, role_at_request="VIEWER", requested_role="VIEWER"
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_submitting_records_an_activity_entry(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        service.submit_request(session, user, "ADMIN")
        session.commit()
        actions = session.execute(
            text("SELECT action FROM user_activity_records")
        ).scalars().all()
        assert "ACCESS_REQUEST_SUBMITTED" in actions

    # -- deciding ------------------------------------------------------------

    def test_approval_changes_the_role_and_closes_the_request(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        approver = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()

        service.approve_request(session, approver, request.id)
        session.commit()

        session.refresh(user)
        session.refresh(request)
        assert user.access_level == "ADMIN"
        assert request.status == "APPROVED"
        assert request.decided_by_user_id == approver.id
        assert request.decided_at is not None

    def test_denial_leaves_the_role_unchanged(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        approver = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()

        service.deny_request(session, approver, request.id)
        session.commit()

        session.refresh(user)
        session.refresh(request)
        assert user.access_level == "VIEWER"
        assert request.status == "DENIED"

    def test_a_denied_request_stays_in_history_and_a_new_one_may_follow(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        approver = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        first = service.submit_request(session, user, "ADMIN")
        session.commit()
        service.deny_request(session, approver, first.id)
        session.commit()

        second = service.submit_request(session, user, "DATA_EDITOR")
        session.commit()

        assert second.id != first.id
        assert session.execute(text("SELECT count(*) FROM access_requests")).scalar_one() == 2

    def test_first_decision_wins(self, session):
        """Two Super Admins act on one request; the second is refused."""
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        first_approver = make_user(session, "sa1@chelsongordon.com", "SUPER_ADMIN")
        second_approver = make_user(session, "sa2@chelsongordon.com", "SUPER_ADMIN")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()

        service.approve_request(session, first_approver, request.id)
        session.commit()

        with pytest.raises(service.RequestAlreadyDecided):
            service.deny_request(session, second_approver, request.id)
        session.rollback()

        session.refresh(request)
        session.refresh(user)
        assert request.status == "APPROVED"
        assert request.decided_by_user_id == first_approver.id
        assert user.access_level == "ADMIN"

    def test_a_genuine_race_produces_exactly_one_decision(self, test_factory, session):
        """Two concurrent transactions on two real database connections.

        Both Super Admins load the request while it is still PENDING — that is
        the window a "read it, check it, write it" implementation would lose in.
        The conditional `UPDATE ... WHERE status = 'PENDING'` closes it: the
        second writer blocks on the row lock until the first commits, and then
        matches zero rows.
        """
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        sa1 = make_user(session, "sa1@chelsongordon.com", "SUPER_ADMIN")
        sa2 = make_user(session, "sa2@chelsongordon.com", "SUPER_ADMIN")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()
        request_id, user_id, sa1_id, sa2_id = request.id, user.id, sa1.id, sa2.id

        with test_factory() as a, test_factory() as b:
            approver_a = a.get(User, sa1_id)
            approver_b = b.get(User, sa2_id)

            # Both see PENDING.
            assert a.get(AccessRequest, request_id).status == "PENDING"
            assert b.get(AccessRequest, request_id).status == "PENDING"

            # A decides first, but has not committed yet.
            service.approve_request(a, approver_a, request_id)

            # B tries to deny the same request. A short lock timeout turns the
            # wait into a visible error instead of an indefinite block — the
            # point being that PostgreSQL will not let both writes proceed.
            b.execute(text("SET LOCAL lock_timeout = '750ms'"))
            with pytest.raises(Exception) as blocked:
                service.deny_request(b, approver_b, request_id)
            assert "lock" in str(blocked.value).lower()
            b.rollback()

            a.commit()

            # Now that A has committed, B sees the truth rather than overwriting it.
            with pytest.raises(service.RequestAlreadyDecided):
                service.deny_request(b, b.get(User, sa2_id), request_id)
            b.rollback()

        session.expire_all()
        final = session.get(AccessRequest, request_id)
        final_user = session.get(User, user_id)

        assert final.status == "APPROVED"
        assert final.decided_by_user_id == sa1_id
        assert final_user.access_level == "ADMIN"
        assert sa2_id != final.decided_by_user_id

    def test_nobody_decides_their_own_request(self, session):
        """Even a Super Admin who somehow has a pending request."""
        sa = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        # Built directly: the service would refuse to create it in the first place.
        request = AccessRequest(
            requester_user_id=sa.id, role_at_request="ADMIN", requested_role="SUPER_ADMIN"
        )
        session.add(request)
        session.commit()

        with pytest.raises(service.CannotDecideOwnRequest):
            service.approve_request(session, sa, request.id)
        session.rollback()

        with pytest.raises(service.CannotDecideOwnRequest):
            service.deny_request(session, sa, request.id)
        session.rollback()

        session.refresh(request)
        assert request.status == "PENDING"

    def test_the_database_forbids_self_approval(self, session):
        sa = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        session.add(
            AccessRequest(
                requester_user_id=sa.id,
                role_at_request="ADMIN",
                requested_role="SUPER_ADMIN",
                status="APPROVED",
                decided_at=text("now()"),
                decided_by_user_id=sa.id,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_a_requester_may_cancel_their_own_request(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()

        service.cancel_request(session, user, request.id)
        session.commit()

        session.refresh(request)
        assert request.status == "CANCELLED"
        # Cancelled, not deleted: history is preserved.
        assert session.execute(text("SELECT count(*) FROM access_requests")).scalar_one() == 1

    def test_cancelling_frees_the_user_to_request_a_different_role(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        first = service.submit_request(session, user, "SUPER_ADMIN")
        session.commit()
        service.cancel_request(session, user, first.id)
        session.commit()

        second = service.submit_request(session, user, "DATA_EDITOR")
        session.commit()
        assert second.status == "PENDING"

    def test_a_user_cannot_cancel_somebody_elses_request(self, session):
        user = make_user(session, "viewer@chelsongordon.com", "VIEWER")
        other = make_user(session, "other@chelsongordon.com", "VIEWER")
        request = service.submit_request(session, user, "ADMIN")
        session.commit()

        with pytest.raises(service.AccessRequestError):
            service.cancel_request(session, other, request.id)


# ===========================================================================
# Direct role management
# ===========================================================================


class TestRoleManagement:
    def test_super_admin_can_promote_and_demote(self, session):
        actor = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        make_user(session, "spare@chelsongordon.com", "SUPER_ADMIN")
        target = make_user(session, "target@chelsongordon.com", "VIEWER")
        session.commit()

        service.change_role(session, actor, target.id, "ADMIN")
        session.commit()
        session.refresh(target)
        assert target.access_level == "ADMIN"

        service.change_role(session, actor, target.id, "VIEWER")
        session.commit()
        session.refresh(target)
        assert target.access_level == "VIEWER"

    def test_a_role_change_is_recorded(self, session):
        actor = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        target = make_user(session, "target@chelsongordon.com", "VIEWER")
        session.commit()
        service.change_role(session, actor, target.id, "DATA_EDITOR")
        session.commit()
        actions = session.execute(text("SELECT action FROM user_activity_records")).scalars().all()
        assert "ROLE_CHANGED" in actions

    def test_a_super_admin_cannot_change_their_own_role(self, session):
        actor = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        make_user(session, "spare@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        with pytest.raises(service.CannotChangeOwnRole):
            service.change_role(session, actor, actor.id, "VIEWER")

    def test_the_last_super_admin_cannot_be_demoted(self, session):
        actor = make_user(session, "sa1@chelsongordon.com", "SUPER_ADMIN")
        last = make_user(session, "sa2@chelsongordon.com", "SUPER_ADMIN")
        session.commit()

        # Two exist, so demoting one is fine.
        service.change_role(session, actor, last.id, "ADMIN")
        session.commit()

        # `actor` is now the only Super Admin, and cannot demote themselves.
        with pytest.raises(service.CannotChangeOwnRole):
            service.change_role(session, actor, actor.id, "ADMIN")

        # Nor can another Super Admin be created and then remove the last one:
        # the protection counts, it does not assume there are four.
        other = make_user(session, "sa3@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        service.change_role(session, other, actor.id, "ADMIN")
        session.commit()
        with pytest.raises(service.LastSuperAdminError):
            service.change_role(session, actor, other.id, "VIEWER")

    def test_the_protection_holds_with_exactly_one_super_admin(self, session):
        only = make_user(session, "only@chelsongordon.com", "SUPER_ADMIN")
        actor = make_user(session, "helper@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        service.change_role(session, only, actor.id, "ADMIN")
        session.commit()
        assert count_active_super_admins(session) == 1

        with pytest.raises(service.CannotChangeOwnRole):
            service.change_role(session, only, only.id, "VIEWER")

    def test_the_last_super_admin_cannot_be_disabled(self, session):
        actor = make_user(session, "sa1@chelsongordon.com", "SUPER_ADMIN")
        other = make_user(session, "sa2@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        service.change_role(session, actor, other.id, "ADMIN")
        session.commit()

        helper = make_user(session, "sa3@chelsongordon.com", "SUPER_ADMIN")
        session.commit()
        service.change_role(session, helper, actor.id, "ADMIN")
        session.commit()

        with pytest.raises(service.LastSuperAdminError):
            service.change_account_status(session, actor, helper.id, "DISABLED")

    def test_disabling_an_account_is_recorded(self, session):
        actor = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        target = make_user(session, "target@chelsongordon.com", "VIEWER")
        session.commit()
        service.change_account_status(session, actor, target.id, "DISABLED")
        session.commit()
        session.refresh(target)
        assert target.account_status == "DISABLED"
        actions = session.execute(text("SELECT action FROM user_activity_records")).scalars().all()
        assert "ACCOUNT_STATUS_CHANGED" in actions

    def test_changing_to_the_same_role_is_refused(self, session):
        actor = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        target = make_user(session, "target@chelsongordon.com", "ADMIN")
        session.commit()
        with pytest.raises(service.AccessRequestError):
            service.change_role(session, actor, target.id, "ADMIN")

    def test_an_unknown_role_is_refused(self, session):
        actor = make_user(session, "sa@chelsongordon.com", "SUPER_ADMIN")
        target = make_user(session, "target@chelsongordon.com", "VIEWER")
        session.commit()
        with pytest.raises(service.InvalidRequestedRole):
            service.change_role(session, actor, target.id, "STUDENT_DATA_OFFICER")


# ===========================================================================
# Identity helpers
# ===========================================================================


def test_identity_lookup_requires_both_tenant_and_object_id(session):
    resolve_user(session, claims("person@chelsongordon.com"))
    session.commit()
    other_tenant = claims("person@chelsongordon.com", tenant=OTHER_TENANT)
    assert find_user_by_identity(session, other_tenant) is None


def test_active_super_admin_count_ignores_disabled_accounts(session):
    make_user(session, "sa1@chelsongordon.com", "SUPER_ADMIN")
    make_user(session, "sa2@chelsongordon.com", "SUPER_ADMIN", status="DISABLED")
    session.commit()
    assert count_active_super_admins(session) == 1
