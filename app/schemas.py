
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["buyer", "supplier", "admin"] = "supplier"
    company_name: str = Field(default="", max_length=180)

    @field_validator("name", "company_name")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError("Name must contain at least 2 characters")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    company_name: str

    model_config = ConfigDict(from_attributes=True)


class TenderCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(default="", max_length=10000)
    category: str = Field(default="General", max_length=100)
    quantity: int = Field(default=1, ge=1)
    tender_type: Literal["rfq", "sealed", "reverse_auction"] = "rfq"
    deadline: datetime
    mandatory_requirements: str = Field(default="", max_length=5000)

    w_price: float = Field(default=0.35, ge=0, le=1)
    w_delivery: float = Field(default=0.20, ge=0, le=1)
    w_trust: float = Field(default=0.25, ge=0, le=1)
    w_match: float = Field(default=0.20, ge=0, le=1)

    anti_sniping: bool = True

    @field_validator("title", "category", "description", "mandatory_requirements")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if len(value) < 4:
            raise ValueError("Title must contain at least 4 non-whitespace characters")
        return value

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "Deadline must include a timezone, for example +05:30 or Z"
            )
        return value


class TenderOut(BaseModel):
    id: int
    buyer_id: int
    title: str
    description: str
    category: str
    quantity: int
    tender_type: str
    deadline: datetime
    status: str
    mandatory_requirements: str
    w_price: float
    w_delivery: float
    w_trust: float
    w_match: float
    anti_sniping: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BidCreate(BaseModel):
    price: float = Field(gt=0, allow_inf_nan=False)
    delivery_days: int = Field(ge=1, le=3650)
    validity_days: int = Field(default=30, ge=1, le=365)
    requirement_match: float = Field(
        default=100, ge=0, le=100, allow_inf_nan=False
    )
    mandatory_met: bool = True
    compliance_notes: str = Field(default="", max_length=5000)

    @field_validator("compliance_notes")
    @classmethod
    def strip_compliance_notes(cls, value: str) -> str:
        return value.strip()


class BidOut(BaseModel):
    id: int
    tender_id: int
    supplier_id: int
    price: float
    delivery_days: int
    validity_days: int
    requirement_match: float
    mandatory_met: bool
    compliance_notes: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenderStatusUpdate(BaseModel):
    status: Literal["closed", "cancelled"]


class SupplierOutcomeIn(BaseModel):
    supplier_id: int = Field(gt=0)
    quality_score: float = Field(
        ge=1, le=5, allow_inf_nan=False
    )
    on_time: bool
    issue_count: int = Field(default=0, ge=0, le=100)
    notes: str = Field(default="", max_length=2000)

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str) -> str:
        return value.strip()
