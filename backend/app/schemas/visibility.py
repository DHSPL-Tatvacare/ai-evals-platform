"""Pydantic helpers for canonical asset visibility handling."""

from pydantic import field_serializer, field_validator

from app.models.mixins.shareable import Visibility


class VisibilityInputMixin:
    """Normalize legacy visibility input to canonical request values."""

    @field_validator("visibility", mode="before", check_fields=False)
    @classmethod
    def normalize_visibility_input(cls, value):
        if value is None:
            return None
        return Visibility.normalize(value)


class VisibilityOutputMixin:
    """Serialize visibility using canonical product vocabulary."""

    @field_serializer("visibility", check_fields=False)
    def serialize_visibility(self, value):
        normalized = Visibility.normalize(value)
        return normalized.value if normalized is not None else None
