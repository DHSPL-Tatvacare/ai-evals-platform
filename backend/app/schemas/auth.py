"""Request/response schemas for auth routes."""
from pydantic import Field

from app.schemas.base import CamelModel


class LoginRequest(CamelModel):
    email: str = Field(
        description="Email address of the account. Matched case-insensitively.",
        examples=["jane@acme.com"],
    )
    password: str = Field(
        description="The account password.",
        examples=["S3cure!pass"],
    )


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(
        description="The current password. Must match the password on file.",
        examples=["S3cure!pass"],
    )
    new_password: str = Field(
        description=(
            "The new password. Minimum 8 characters and must contain an uppercase "
            "letter, a lowercase letter, a digit, and a special character. Must "
            "differ from the current password."
        ),
        examples=["N3w!Secur3pass"],
    )


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
    token: str = Field(
        description="The single-use invite token from the invite link sent to the user.",
        examples=["8f3c1d9a4b7e2f60a1c5d8e9f0b2a3c4"],
    )
    email: str = Field(
        description=(
            "Email for the new account. If the tenant restricts email domains, this "
            "must match one of the permitted domains."
        ),
        examples=["jane@acme.com"],
    )
    password: str = Field(
        description=(
            "Password for the new account. Minimum 8 characters and must contain an "
            "uppercase letter, a lowercase letter, a digit, and a special character."
        ),
        examples=["N3w!Secur3pass"],
    )
    display_name: str = Field(
        description="Full name shown across the platform UI.",
        examples=["Jane Cooper"],
    )


class ValidateInviteResponse(CamelModel):
    valid: bool
    tenant_name: str | None = None
    default_role: str | None = None
    expires_at: str | None = None
    allowed_domains: list[str] = []
