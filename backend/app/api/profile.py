from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.onboarding import (
    ArchetypeResultOut,
    ArchetypeSubmission,
    CharacterOut,
    CharacterUpdate,
    GoalIn,
    GoalOut,
    KinkSheetIn,
    SoContextIn,
    ToyIn,
    ToyOut,
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


@router.put("/{profile_id}/kinks")
async def put_kinks(
    profile_id: uuid.UUID,
    body: KinkSheetIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await svc.replace_kinks(session, profile_id, body.entries)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return {"count": len(body.entries)}


@router.post("/{profile_id}/toys", response_model=ToyOut, status_code=status.HTTP_201_CREATED)
async def add_toy(
    profile_id: uuid.UUID,
    body: ToyIn,
    session: AsyncSession = Depends(get_session),
) -> ToyOut:
    try:
        toy = await svc.add_toy(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return ToyOut.model_validate(toy)


@router.get("/{profile_id}/toys", response_model=list[ToyOut])
async def list_toys(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ToyOut]:
    try:
        toys = await svc.list_toys(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    return [ToyOut.model_validate(t) for t in toys]


@router.post("/{profile_id}/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def add_goal(
    profile_id: uuid.UUID,
    body: GoalIn,
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    try:
        goal = await svc.add_goal(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return GoalOut.model_validate(goal)


@router.get("/{profile_id}/goals", response_model=list[GoalOut])
async def list_goals(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[GoalOut]:
    try:
        goals = await svc.list_goals(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    return [GoalOut.model_validate(g) for g in goals]


@router.put("/{profile_id}/so-context", response_model=SoContextIn)
async def put_so_context(
    profile_id: uuid.UUID,
    body: SoContextIn,
    session: AsyncSession = Depends(get_session),
) -> SoContextIn:
    try:
        so = await svc.upsert_so_context(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return SoContextIn(description=so.description, values=so.values, dynamic=so.dynamic)


@router.get("/{profile_id}/character", response_model=CharacterOut)
async def get_character(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CharacterOut:
    try:
        char = await svc.get_character(session, profile_id)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    return CharacterOut.model_validate(char)


@router.put("/{profile_id}/character", response_model=CharacterOut)
async def update_character(
    profile_id: uuid.UUID,
    body: CharacterUpdate,
    session: AsyncSession = Depends(get_session),
) -> CharacterOut:
    try:
        char = await svc.update_character(session, profile_id, body)
    except svc.ProfileNotFound:
        raise _not_found(profile_id)
    await session.commit()
    return CharacterOut.model_validate(char)
