from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address", examples=["admin@test.com"])
    password: str = Field(..., description="User password", examples=["AdminTest123!"])

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Password must not be empty.")
        return v


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token (15-minute expiry)")
    refresh_token: str = Field(..., description="JWT refresh token (7-day expiry)")
    token_type: str = Field("bearer", examples=["bearer"])
    must_change_password: bool = Field(
        False,
        description="True if the user should be prompted to change their password",
    )


class AccessTokenResponse(BaseModel):
    access_token: str = Field(..., description="New JWT access token (15-minute expiry)")
    token_type: str = Field("bearer", examples=["bearer"])


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        ..., description="A valid, non-revoked refresh token obtained from /login"
    )

    @field_validator("refresh_token")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("refresh_token must not be empty.")
        return v


class LogoutRequest(BaseModel):
    refresh_token: str = Field(
        ..., description="The refresh token to revoke. Subsequent refresh attempts will fail."
    )

    @field_validator("refresh_token")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("refresh_token must not be empty.")
        return v
