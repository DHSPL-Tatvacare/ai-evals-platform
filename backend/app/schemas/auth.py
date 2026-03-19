"""Request/response schemas for auth routes."""
from app.schemas.base import CamelModel


class LoginRequest(CamelModel):
    email: str
    password: str


class ChangePasswordRequest(CamelModel):
    current_password: str
    new_password: str


class UserResponse(CamelModel):
    id: str
    email: str
    display_name: str
    role: str
    tenant_id: str
    tenant_name: str


class TokenResponse(CamelModel):
    access_token: str
    user: UserResponse


class SignupRequest(CamelModel):
    token: str
    email: str
    password: str
    display_name: str


class ValidateInviteResponse(CamelModel):
    valid: bool
    tenant_name: str | None = None
    default_role: str | None = None
    expires_at: str | None = None
    allowed_domains: list[str] = []
