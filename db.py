# -*- coding: utf-8 -*-
"""
db.py
------
مدل‌های دیتابیس مشترک بین ربات بله و پنل مدیریت وب.
از PostgreSQL (متغیر محیطی DATABASE_URL) استفاده می‌کند.
"""
import os
import datetime

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    LargeBinary,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local_dev.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)

    newspaper_name = Column(String(255), nullable=False)
    journalist_name = Column(String(255), nullable=False)
    headline = Column(Text, nullable=False)
    publish_date = Column(String(64), nullable=False)

    file_id = Column(String(255), nullable=False)
    file_kind = Column(String(32), nullable=False)

    file_data = Column(LargeBinary, nullable=True)
    file_mimetype = Column(String(128), nullable=True)
    original_filename = Column(String(255), nullable=True)

    bale_user_id = Column(String(64), nullable=True)
    bale_chat_id = Column(String(64), nullable=True)

    auto_score = Column(Integer, nullable=False, default=0)
    final_score = Column(Integer, nullable=True)
    is_front_page = Column(Boolean, nullable=True)
    admin_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    @property
    def effective_score(self) -> int:
        return self.final_score if self.final_score is not None else self.auto_score


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
