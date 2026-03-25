"""Request/response schemas for external agents."""

from app.schemas.base import CamelORMModel


class ExternalAgentResponse(CamelORMModel):
    id: str
    tenant_id: str
    source: str
    external_id: str
    name: str
    email: str | None = None
