from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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

app.include_router(api_router, prefix="/api/v1")

# Serve uploaded files (photos, etc.) - works both in dev and behind nginx
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
if os.path.isdir(UPLOAD_DIR):
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/")
async def root():
    return {"message": "海外仓财务管理系统 API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok"}
