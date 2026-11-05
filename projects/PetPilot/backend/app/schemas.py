from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


# ---------- API 入参 / 出参 ----------
class LoginRequest(BaseModel):
    code: str


class LoginResponse(BaseModel):
    token: str


class PetCreate(BaseModel):
    name: str


class PetOut(BaseModel):
    id: int
    name: str


class MessageIn(BaseModel):
    text: str


class FactOut(BaseModel):
    id: int
    pet_id: int
    pet_name: str
    topic: str | None = None
    value: float | None = None
    unit: str | None = None
    quote: str
    version: int


class HeldOut(BaseModel):
    id: int
    quote: str
    reason: str


class MessageResult(BaseModel):
    message_id: int
    facts: list[FactOut] = []
    held_segments: list[HeldOut] = []
    corrections: list[dict] = []
    reminders: list[dict] = []
    care_requests: list[dict] = []
    photos: list[dict] = []
    answer: str = ""
    explanation: str = ""
    receipt: str = ""


class ReminderOut(BaseModel):
    id: int
    pet_name: str | None = None
    quote: str
    due_at: str | None = None
    status: str
    is_due: bool = False


class PhotoOut(BaseModel):
    id: int
    pet_name: str | None = None
    filename: str
    description: str = ""


class CareSummaryOut(BaseModel):
    id: int
    pet_name: str
    title: str
    summary: str


# ---------- 模型输出信封（宽松解析） ----------
class AddObservation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["add_observation"] = "add_observation"
    op_id: str = ""
    start: int = 0
    end: int = 0
    quote: str = ""
    pet_id: int | None = None
    topic: str | None = None
    value: float | None = None
    unit: str | None = None
    quantity_scope: str | None = None
    historical_current: str | None = None
    occurred_at: str | None = None
    polarity: str | None = None
    change_kind: str = "new"

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        try:
            return float(str(v))
        except (TypeError, ValueError):
            return None

    @field_validator("pet_id", mode="before")
    @classmethod
    def _coerce_pet_id(cls, v):
        if v is None or isinstance(v, int):
            return v
        s = str(v).strip()
        return int(s) if s.isdigit() else None


class HoldSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["hold_segment"] = "hold_segment"
    op_id: str = ""
    start: int = 0
    end: int = 0
    quote: str = ""
    reason: str = "归属未知"
    topic: str | None = None
    value: float | None = None
    unit: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v):
        if v is None or isinstance(v, (int, float)):
            return v
        try:
            return float(str(v))
        except (TypeError, ValueError):
            return None


class RawModelOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    operations: list[dict] = []
    dialogue: dict = {}
