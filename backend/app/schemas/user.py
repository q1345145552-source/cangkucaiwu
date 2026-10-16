from pydantic import BaseModel, Field
from datetime import datetime
from app.core.permissions import Role

class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    role: Role = Role.STAFF
    warehouse_id: int | None = None
    warehouse_ids: list[int] | None = None  # 多仓分配（主管）

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    extra_permissions: list[str] | None = None  # 扩展权限（主管/财务）

class UserUpdate(BaseModel):
    display_name: str | None = None
    username: str | None = None
    password: str | None = None
    role: Role | None = None
    warehouse_id: int | None = None
    warehouse_ids: list[int] | None = None  # 多仓分配（主管）
    is_active: bool | None = None
    line_user_id: str | None = None
    extra_permissions: list[str] | None = None
    attendance_enabled: bool | None = None

class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    extra_permissions: list[str] | None = None
    attendance_enabled: bool = False
    attendance_employee_id: int | None = None
    attendance_enabled_at: datetime | None = None
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True
