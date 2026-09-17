# -*- coding: utf-8 -*-
"""
db.py
------
مدل‌های دیتابیس مشترک بین ربات بله و پنل مدیریت وب.
از PostgreSQL (متغیر محیطی DATABASE_URL که ریلوی به‌صورت خودکار می‌سازد) استفاده می‌کند.
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
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# اتصال به دیتابیس
# ---------------------------------------------------------------------------
# ریلوی معمولاً متغیر DATABASE_URL را با پیشوند postgres:// می‌دهد که
# SQLAlchemy نسخه جدید به postgresql:// نیاز دارد؛ این خط آن را اصلاح می‌کند.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local_dev.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Submission(Base):
    """هر رکورد یعنی یک خبر که یک خبرنگار از طریق ربات ارسال کرده است."""

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)

    # اطلاعاتی که خود خبرنگار در گفتگو با ربات وارد می‌کند
    newspaper_name = Column(String(255), nullable=False)
    journalist_name = Column(String(255), nullable=False)
    headline = Column(Text, nullable=False)
    publish_date = Column(String(64), nullable=False)  # تاریخ به شکل متنی (مثلا شمسی) که خبرنگار تایپ می‌کند

    # اطلاعات فایل ارسالی در بله
    file_id = Column(String(255), nullable=False)
    file_kind = Column(String(32), nullable=False)  # "document" یا "photo"

    # شناسایی خبرنگار در بله (برای پیگیری‌های بعدی)
    bale_user_id = Column(String(64), nullable=True)
    bale_chat_id = Column(String(64), nullable=True)

    # امتیازدهی
    auto_score = Column(Integer, nullable=False, default=0)
    final_score = Column(Integer, nullable=True)  # تا وقتی ادمین اصلاح نکرده خالی می‌ماند
    is_front_page = Column(Boolean, nullable=True)  # تشخیص نهایی صفحه اول بودن، فقط توسط ادمین
    admin_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    @property
    def effective_score(self) -> int:
        """امتیازی که باید در گزارش‌ها و جمع‌بندی‌ها استفاده شود."""
        return self.final_score if self.final_score is not None else self.auto_score


def init_db():
    """جدول‌ها را در صورت نبودن می‌سازد. در شروع هم ربات و هم پنل وب صدا زده می‌شود."""
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
