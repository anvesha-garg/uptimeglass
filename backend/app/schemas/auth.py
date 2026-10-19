from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class _EmailModel(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        # The database stores emails in lowercase, so one person cannot register twice.
        return value.lower()


class RegisterRequest(_EmailModel):
    # Max length stops someone sending a huge password just to burn CPU in the hasher.
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(_EmailModel):
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
