"""
BrainDump — Pydantic models
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

CATEGORIES = Literal["Work", "Groceries", "Personal", "Other"]


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    status: str
    token: Optional[str] = None
    message: Optional[str] = None


class TaskCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    category: CATEGORIES = "Other"
    due_date: Optional[str] = None   # ISO: YYYY-MM-DD


class TaskUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[CATEGORIES] = None
    done: Optional[bool] = None
    due_date: Optional[str] = Field(None)   # None = keep, "" = clear to NULL


class TaskOut(BaseModel):
    id: int
    text: str
    category: str
    done: bool
    due_date: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "TaskOut":
        return cls(
            id=row["id"],
            text=row["text"],
            category=row["category"],
            done=bool(row["done"]),
            due_date=row["due_date"] if row["due_date"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class ExtractedTask(BaseModel):
    text: str
    category: CATEGORIES = "Other"
    due_date: Optional[str] = None


class ProcessResponse(BaseModel):
    tasks: list[TaskOut]
    raw_extracted: list[ExtractedTask]


class WidgetTask(BaseModel):
    id: int
    text: str
    category: str
    due_date: Optional[str] = None
    overdue: bool = False


class WidgetResponse(BaseModel):
    total_open: int
    today_count: int
    tasks: list[WidgetTask]
