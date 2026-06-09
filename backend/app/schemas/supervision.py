from __future__ import annotations

from pydantic import BaseModel

from app.db.enums import SupervisionMode


class SupervisionOut(BaseModel):
    mode: SupervisionMode
    notes: dict[str, str]


class SetModeIn(BaseModel):
    mode: SupervisionMode


class SetNoteIn(BaseModel):
    mode: SupervisionMode
    note: str = ""
