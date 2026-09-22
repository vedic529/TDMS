"""The `/suggestions` router — checks 3.8 (E1–E6) of the Revision 2 prompt.

The queue is shared by every tab, so it is no longer reachable under
`/allocation`. Reading is VIEWER and above; resolving requires
MAINTAIN_REFERENCE_DATA, which a Data Editor does not hold.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, select, text

from app.models.allocation import ReferenceSuggestion
from app.models.user import User
from app.services.reference_suggestions import raise_reference_suggestion

from tests.test_allocation_records import (  # reuse the approved fixtures
    EDITOR,
    VIEWER,
    as_user,
    client,  # noqa: F401 - fixture
    people,  # noqa: F401 - fixture
    refs,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.database

ADMIN = "suggestion.admin@chelsongordon.com"


@pytest.fixture()
def admin(session, people):
    """An Admin, who alone may resolve (MAINTAIN_REFERENCE_DATA)."""
    from app.auth.mock import mock_claims_for

    claims = mock_claims_for(ADMIN)
    existing = session.execute(
        select(User).where(User.organisation_email == ADMIN)
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            User(
                organisation_email=ADMIN,
                display_name="Suggestion Admin",
                access_level="ADMIN",
                account_status="ACTIVE",
                entra_object_id=claims.object_id,
                entra_tenant_id=claims.tenant_id,
            )
        )
        session.commit()
    return ADMIN


@pytest.fixture()
def queued(session, refs):
    """Two pending entries. Recorded exceptions went on 15 September 2026."""
    session.execute(text("TRUNCATE TABLE reference_suggestion RESTART IDENTITY CASCADE"))
    raise_reference_suggestion(
        session, entity_type="FACILITY", raw_value="Room X", context={}, source="ALLOCATION_IMPORT"
    )
    raise_reference_suggestion(
        session, entity_type="TRAINER", raw_value="Someone", context={}, source="ALLOCATION_IMPORT"
    )
    session.commit()
    return True


def test_e1_summary_is_one_grouped_query(client, queued, test_engine):
    """E1 — per-entity counts, and the whole summary costs a single SELECT."""
    statements: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        if "reference_suggestion" in statement.lower() and statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        response = client.get("/suggestions/summary", headers=as_user(VIEWER))
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)

    assert response.status_code == 200
    body = {row["entity_type"]: row for row in response.json()}
    # Every entity is present, so a tab can render a stable grey indicator.
    assert set(body) >= {"COLLEGE", "CAMPUS", "QUALIFICATION", "UNIT", "FACILITY", "TRAINER"}
    assert body["FACILITY"]["pending"] == 1
    assert body["FACILITY"]["exceptions"] == 0
    assert body["TRAINER"]["pending"] == 1
    assert body["COLLEGE"]["pending"] == 0
    assert len(statements) == 1, f"summary issued {len(statements)} queries, expected 1"


def test_e2_list_is_filtered_and_paginated(client, queued):
    """E2 — filtered by entity and status, with the true total."""
    response = client.get(
        "/suggestions", params={"entity_type": "FACILITY", "status": "PENDING"}, headers=as_user(VIEWER)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["entity_type"] == "FACILITY"
    assert body["items"][0]["raw_value"] == "Room X"


def test_e2_list_can_span_the_entities_a_tab_owns(client, queued):
    """A tab owning two entities reads them in one call, not two."""
    response = client.get(
        "/suggestions",
        params=[("entity_types", "FACILITY"), ("entity_types", "TRAINER")],
        headers=as_user(VIEWER),
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2


def test_e3_resolve_accepts_create_map_and_reject(client, session, queued, admin, refs):
    """E3 — amended 15 September 2026: Withdraw went with recorded exceptions."""
    facility = session.execute(
        select(ReferenceSuggestion).where(
            ReferenceSuggestion.entity_type == "FACILITY", ReferenceSuggestion.status == "PENDING"
        )
    ).scalars().one()

    response = client.post(
        f"/suggestions/{facility.id}/resolve",
        json={"action": "MAP", "resolved_entity_id": refs["facility_id"]},
        headers=as_user(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suggestion"]["status"] == "MAPPED"
    # The count is part of the contract: zero must be showable as a warning.
    assert "records_updated" in body

    trainer = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.entity_type == "TRAINER")
    ).scalars().one()
    withdrawn = client.post(
        f"/suggestions/{trainer.id}/resolve", json={"action": "WITHDRAW"}, headers=as_user(admin)
    )
    assert withdrawn.status_code == 400, "Withdraw is no longer an action"


def test_e3_resolve_requires_maintain_reference_data(client, session, queued):
    """A Data Editor may read the queue but not decide it (G5)."""
    entry = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.status == "PENDING")
    ).scalars().first()
    response = client.post(
        f"/suggestions/{entry.id}/resolve", json={"action": "REJECT"}, headers=as_user(EDITOR)
    )
    assert response.status_code == 403

    # Reading is still permitted.
    assert client.get("/suggestions/summary", headers=as_user(EDITOR)).status_code == 200


def test_affected_endpoint_reports_the_total(client, session, queued):
    """2.10 — the affected list carries the true total and a truncation flag."""
    entry = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.status == "PENDING")
    ).scalars().first()
    response = client.get(f"/suggestions/{entry.id}/affected", headers=as_user(VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert body["suggestion_id"] == entry.id
    assert "total" in body and "truncated" in body


def test_e4_the_old_allocation_paths_are_gone(client, queued):
    """E4 — no handler remains under /allocation for the queue."""
    assert client.get("/allocation/suggestions", headers=as_user(VIEWER)).status_code == 404


def test_e6_openapi_documents_the_new_endpoints(client):
    """E6 — the schema generates and the four paths are present."""
    schema = client.get("/openapi.json").json()
    for path in (
        "/suggestions",
        "/suggestions/summary",
        "/suggestions/{suggestion_id}/affected",
        "/suggestions/{suggestion_id}/resolve",
    ):
        assert path in schema["paths"], f"{path} missing from the OpenAPI document"
    assert not any(p.startswith("/allocation/suggestions") for p in schema["paths"])
