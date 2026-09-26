"""Inventory request/response models. extra="forbid" blocks mass assignment (e.g. user_id)."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_Description = Field(default=None, min_length=1, max_length=500)
_Manufacturer = Field(default=None, min_length=1, max_length=200)
_Model = Field(default=None, min_length=1, max_length=64)
_Upc = Field(default=None, pattern=r"^\d{8,14}$")
_Category = Field(default=None, min_length=1, max_length=100)
_Year = Field(default=None, ge=1950, le=2100)


class InventoryItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nickname: str = Field(min_length=1, max_length=120)
    description: str | None = _Description
    manufacturer: str | None = _Manufacturer
    model: str | None = _Model
    upc: str | None = _Upc
    category: str | None = _Category
    purchase_year: int | None = _Year

    @model_validator(mode="after")
    def _needs_product_information(self) -> Self:
        if not any((self.description, self.manufacturer, self.model, self.upc)):
            raise ValueError("provide at least one of description, manufacturer, model or upc")
        return self


class InventoryItemUpdate(BaseModel):
    """Partial update: omitted fields are unchanged, explicit null clears a field."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nickname: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = _Description
    manufacturer: str | None = _Manufacturer
    model: str | None = _Model
    upc: str | None = _Upc
    category: str | None = _Category
    purchase_year: int | None = _Year


class InventoryItemOut(BaseModel):
    id: uuid.UUID
    nickname: str
    description: str | None
    manufacturer: str | None
    model: str | None
    upc: str | None
    category: str | None
    purchase_year: int | None
    created_at: datetime
    updated_at: datetime


class InventoryListResponse(BaseModel):
    items: list[InventoryItemOut]
    total: int
    limit: int
    offset: int
