"""The shared reference-suggestion queue.

Every importer raises into this queue and every reference-data tab reads from
it, so it is not an allocation concern and no longer lives under that router.

Reading is VIEWER and above — a user without maintenance rights still sees what
is outstanding. Resolving is ADMIN and above, through
`require_maintain_reference_data`; no handler compares an access level itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_maintain_reference_data, require_viewer_or_above
from app.models.user import User
from app.schemas.allocation import (
    AffectedRecordsRead,
    SuggestionList,
    SuggestionRead,
    SuggestionResolve,
    SuggestionResolveResult,
    SuggestionSummaryRead,
)
from app.services import reference_suggestion_service as service
from app.services.allocation_import import AllocationImportError

router = APIRouter(prefix="/suggestions", tags=["reference suggestions"])

READ_RESPONSES = {403: {"description": "Requires an active TDMS account."}}
WRITE_RESPONSES = {
    403: {"description": "Resolving a suggestion requires Admin access or above."},
    400: {"description": "The decision was refused."},
    404: {"description": "Suggestion not found."},
}


@router.get("/summary", response_model=list[SuggestionSummaryRead], responses=READ_RESPONSES)
def read_summary(
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """Per-entity counts for the tab indicators — one grouped query.

    Every entity type is returned, including those with nothing outstanding, so
    a tab can render a stable grey indicator rather than nothing at all.
    """
    return [SuggestionSummaryRead.model_validate(item) for item in service.summary(session)]


@router.get("", response_model=SuggestionList, responses=READ_RESPONSES)
def list_suggestions(
    entity_type: str | None = Query(default=None),
    entity_types: list[str] | None = Query(default=None),
    status: str = Query(default="PENDING"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """Entries of one status, narrowed to the entity types a tab owns."""
    rows, total = service.list_suggestions(
        session,
        entity_type=entity_type,
        entity_types=entity_types,
        status=status.upper(),
        limit=limit,
        offset=offset,
    )
    return SuggestionList(
        items=[SuggestionRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{suggestion_id}/affected", response_model=AffectedRecordsRead, responses=READ_RESPONSES)
def read_affected(
    suggestion_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_viewer_or_above),
    session: Session = Depends(get_db),
):
    """Which stored records this entry affects. Fetched on demand, never per entry."""
    try:
        return AffectedRecordsRead.model_validate(
            service.affected_records(session, suggestion_id, limit=limit)
        )
    except AllocationImportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{suggestion_id}/resolve", response_model=SuggestionResolveResult, responses=WRITE_RESPONSES)
def resolve_suggestion(
    suggestion_id: int,
    payload: SuggestionResolve,
    actor: User = Depends(require_maintain_reference_data),
    session: Session = Depends(get_db),
):
    """Apply a decision and report how many stored records it repaired."""
    try:
        row, records_updated = service.resolve_suggestion(
            session,
            actor,
            suggestion_id=suggestion_id,
            action=payload.action,
            resolved_entity_id=payload.resolved_entity_id,
        )
        session.commit()
    except AllocationImportError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        session.rollback()
        raise
    return SuggestionResolveResult(
        suggestion=SuggestionRead.model_validate(row), records_updated=records_updated
    )
