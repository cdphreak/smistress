from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.onboarding import ProfileCreate, ProfileCreated
from app.services import profile as svc
from app.services.archetype import MAX_ANSWER, QUESTIONNAIRE
from app.services.kink_catalog import KINK_CATALOG

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/questionnaire")
async def get_questionnaire() -> dict:
    return {
        "statements": list(QUESTIONNAIRE),
        "kinks": list(KINK_CATALOG),
        "answer_scale": {"min": 0, "max": MAX_ANSWER},
    }


@router.post(
    "/profile",
    response_model=ProfileCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    data: ProfileCreate, session: AsyncSession = Depends(get_session)
) -> ProfileCreated:
    if not data.is_adult or not data.consent_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="18+ acknowledgement and consent are required to begin.",
        )
    profile = await svc.create_profile(session, data)
    await session.commit()
    return ProfileCreated(id=profile.id, intensity_ceiling=profile.intensity_ceiling)
