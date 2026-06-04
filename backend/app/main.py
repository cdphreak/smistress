from __future__ import annotations

from fastapi import Depends, FastAPI

from app.config import Settings
from app.llm.factory import build_provider
from app.llm.provider import LLMProvider
from app.llm.types import ChatMessage

settings = Settings()
app = FastAPI(title="smistress")


def get_provider() -> LLMProvider:
    return build_provider(settings)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "vision_enabled": settings.vision_enabled}


@app.post("/llm/ping")
async def llm_ping(provider: LLMProvider = Depends(get_provider)) -> dict:
    result = await provider.chat([ChatMessage(role="user", content="ping")])
    return {"content": result.content}
