from pydantic import BaseModel, Field
from typing import List, Optional

class WarehouseInfo(BaseModel):
    id: int
    name: str
    code: str

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    display_name: str
    role: str
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    warehouses: Optional[List[WarehouseInfo]] = None
    extra_permissions: list | None = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)
