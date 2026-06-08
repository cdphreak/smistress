from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.availability import router as availability_router
from app.api.chat import router as chat_router
from app.api.drones import router as drones_router
from app.api.economy import router as economy_router
from app.api.memory import router as memory_router
from app.api.onboarding import router as onboarding_router
from app.api.persona import router as persona_router
from app.api.profile import router as profile_router
from app.api.safety import router as safety_router
from app.api.tasks import router as tasks_router
from app.config import Settings
from app.db.session import get_session
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage

settings = Settings()
app = FastAPI(title="smistress")
app.include_router(onboarding_router)
app.include_router(profile_router)
app.include_router(persona_router)
app.include_router(memory_router)
app.include_router(tasks_router)
app.include_router(economy_router)
app.include_router(safety_router)
app.include_router(chat_router)
app.include_router(availability_router)
app.include_router(drones_router)


def get_provider() -> LLMProvider:
    return build_provider(settings)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "vision_enabled": settings.vision_enabled}


@app.get("/db/health")
async def db_health(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {"database": "ok"}


@app.post("/llm/ping")
async def llm_ping(provider: LLMProvider = Depends(get_provider)) -> dict:
    result = await provider.chat([ChatMessage(role="user", content="ping")])
    return {"content": result.content}
