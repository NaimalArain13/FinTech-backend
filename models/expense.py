from typing import Literal, Optional

from pydantic import BaseModel, Field


class EntryMeta(BaseModel):
    voiceText: Optional[str] = None
    asrConfidence: Optional[float] = Field(default=None, ge=0, le=1)
    lang: Optional[str] = None


class EntryCreate(BaseModel):
    entryType: Literal["expense", "income"]
    category: str
    amount: float
    currency: str = Field(default="PKR", min_length=1)
    paymentMethod: str = Field(default="cash")
    notes: Optional[str] = None
    recordedBy: Literal["voice", "manual"] = "manual"
    deviceId: Optional[str] = None
    meta: Optional[EntryMeta] = None


class EntryResponse(BaseModel):
    id: str = Field(alias="_id")
    type: Literal["entry"]
    entryType: Literal["expense", "income"]
    category: str
    amount: float
    currency: str
    paymentMethod: str
    notes: Optional[str]
    createdAt: str
    recordedBy: Literal["voice", "manual"]
    deviceId: Optional[str]
    syncStatus: Literal["local", "synced", "conflict"]
    meta: Optional[EntryMeta]
