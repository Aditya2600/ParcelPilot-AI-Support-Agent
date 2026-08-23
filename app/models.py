from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


Role = Literal["customer", "support_agent", "ops_manager"]


class Principal(BaseModel):
    user_id: str
    role: Role
    account_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    principal: Principal


class ChatResponse(BaseModel):
    answer: str
    confidence: Literal["high", "medium", "low"]
    tool_trace: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    pending_action: dict[str, Any] | None = None


class ConfirmRequest(BaseModel):
    confirmation_token: str
    principal: Principal

