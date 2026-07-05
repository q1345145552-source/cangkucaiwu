from pydantic import BaseModel, Field
from datetime import datetime
from app.core.permissions import Role

class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    role: Role = Role.STAFF
    warehouse_id: int | None = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class UserUpdate(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    warehouse_id: int | None = None
    is_active: bool | None = None
    line_user_id: str | None = None
    extra_permissions: list[str] | None = None

class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    extra_permissions: list[str] | None = None
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True
