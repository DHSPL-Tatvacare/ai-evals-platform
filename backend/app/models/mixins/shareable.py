"""Shared ownership primitives for assets that can be private or shared."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class Visibility(str, enum.Enum):
    """Visibility values supported during the staged shared-visibility rollout."""

    PRIVATE = "private"
    SHARED = "shared"
    APP = "app"

    @classmethod
    def normalize(cls, value: "Visibility | str | None") -> "Visibility | None":
        """Return the canonical visibility for API and application logic."""

        if value is None:
            return None
        if isinstance(value, cls):
            return cls.SHARED if value in {cls.SHARED, cls.APP} else cls.PRIVATE

        normalized = str(value).strip().lower()
        if normalized == cls.PRIVATE.value:
            return cls.PRIVATE
        if normalized in {cls.SHARED.value, cls.APP.value}:
            return cls.SHARED
        raise ValueError(f"Unsupported visibility value: {value}")

    def is_shared(self) -> bool:
        return self in {Visibility.SHARED, Visibility.APP}


def shared_visibility_values() -> tuple[Visibility, Visibility]:
    """Return both canonical and legacy shared enum members for staged queries."""

    return (Visibility.SHARED, Visibility.APP)


class ShareableMixin:
    """Common sharing metadata for shareable asset families.

    Models still declare their own ``forked_from`` column because the FK type
    differs by table.
    """

    visibility: Mapped[Visibility] = mapped_column(
        SAEnum(Visibility, name="asset_visibility", native_enum=False),
        nullable=False,
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
    )
    shared_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    shared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


def shareable_uuid_forked_from(table_name: str) -> Mapped[uuid.UUID | None]:
    """Build a nullable same-table UUID FK for shareable assets."""

    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{table_name}.id", ondelete="SET NULL"),
        nullable=True,
    )


def shareable_int_forked_from(table_name: str) -> Mapped[int | None]:
    """Build a nullable same-table integer FK for shareable assets."""

    return mapped_column(
        ForeignKey(f"{table_name}.id", ondelete="SET NULL"),
        nullable=True,
    )
