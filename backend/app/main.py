from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.api.v1.router import api_router

app = FastAPI(
    title="海外仓财务管理系统 Warehouse Finance System",
    description="ระบบการจัดการการเงินคลังสินค้าต่างประเทศ",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 审计日志：自动记录所有成功的写操作到 audit_logs 表
from app.core.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)

app.include_router(api_router, prefix="/api/v1")

from app.api.secure_uploads import router as secure_uploads_router
app.include_router(secure_uploads_router)

@app.get("/")
async def root():
    return {"message": "海外仓财务管理系统 API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.middleware("http")
async def private_response_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/v1/", "/uploads/")):
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "") if "no-store" in response.headers.get("Cache-Control", "") else "private, no-store"
        response.headers["Vary"] = "Authorization, Cookie, X-Warehouse-ID"
    return response
