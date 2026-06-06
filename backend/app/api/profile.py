from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
)
from app.services import profile as svc
from app.services.archetype import score_archetypes, unknown_answer_ids

router = APIRouter(prefix="/profile", tags=["profile"])


def _not_found(profile_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"profile {profile_id} not found",
    )


@router.post("/{profile_id}/archetype", response_model=ArchetypeResultOut)
async def submit_archetype(
    profile_id: uuid.UUID,
    body: ArchetypeSubmission,
    session: AsyncSession = Depends(get_session),
) -> ArchetypeResultOut:
    bad = unknown_answer_ids(body.answers)
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown questionnaire ids: {sorted(bad)}",
        )
    scores = score_archetypes(body.answers)
    try:
        await svc.add_archetype_result(session, profile_id, body.answers, scores)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return ArchetypeResultOut(scores=scores)
