"""Prompt model - versioned LLM prompt templates."""
from sqlalchemy import String, Text, Integer, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, TenantUserMixin


class Prompt(Base, TimestampMixin, TenantUserMixin):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "app_id", "prompt_type", "version", "user_id", name="uq_prompt_version"),
        Index("idx_prompts_tenant", "tenant_id"),
        Index("idx_prompts_tenant_user", "tenant_id", "user_id"),
        Index("idx_prompts_tenant_app", "tenant_id", "app_id"),
    )
