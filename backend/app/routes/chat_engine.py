"""API routes for the chat engine."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import AuthContext, get_auth_context

router = APIRouter(prefix="/api/chat-engine", tags=["chat-engine"])


@router.get("/defaults")
async def get_defaults(auth: AuthContext = Depends(get_auth_context)):
    """Return default model per provider for the chat widget."""
    return {
        "openai": {
            "model": "gpt-5.4",
        },
    }
