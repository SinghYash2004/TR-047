import os
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import ForeignKey, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./incidents.db")


class Base(DeclarativeBase):
    __abstract__ = True


class IncidentORM(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    readme: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[str | None] = mapped_column(Text)
    end_time: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class LogEventORM(Base):
    __tablename__ = "log_events"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    timestamp: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_file: Mapped[str | None] = mapped_column(Text)
    service: Mapped[str | None] = mapped_column(Text, index=True)
    level: Mapped[str | None] = mapped_column(Text, index=True)
    message: Mapped[str | None] = mapped_column(Text)
    parsed_fields: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class RCAResultORM(Base):
    __tablename__ = "rca_results"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), unique=True, nullable=False)
    rca_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class ReportORM(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), unique=True, nullable=False)
    markdown: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    # Ensure local SQLite parent folders exist before SQLAlchemy opens the file.
    if DATABASE_URL.startswith("sqlite+aiosqlite:///"):
        sqlite_path = DATABASE_URL.removeprefix("sqlite+aiosqlite:///")
        db_path = Path(sqlite_path)
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
