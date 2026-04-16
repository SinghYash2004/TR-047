import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.database import init_db
from routers.ai import router as ai_router
from routers.analysis import router as analysis_router
from routers.report import router as report_router
from routers.upload import router as upload_router


load_dotenv()
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))


def _allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in configured.split(",") if origin.strip() and "*" not in origin]


def _allowed_origin_regex() -> str | None:
    configured = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    patterns = []
    for origin in configured.split(","):
        origin = origin.strip()
        if not origin or "*" not in origin:
            continue
        escaped = origin.replace(".", r"\.").replace("*", ".*")
        patterns.append(escaped)
    if not patterns:
        return r"https://.*\.vercel\.app"
    return "|".join(f"^{pattern}$" for pattern in patterns)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Autonomous Log-to-Incident Report Generator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=_allowed_origin_regex(),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(upload_router)
app.include_router(analysis_router)
app.include_router(ai_router)
app.include_router(report_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
