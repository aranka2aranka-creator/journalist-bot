# -*- coding: utf-8 -*-
"""
bot.py
------
ربات بله برای دریافت بازتاب‌های خبری از خبرنگاران.
"""
import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import bale

from db import Submission, get_session, init_db
from scoring import compute_auto_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("journalist-bot")


class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("ربات فعال است.".encode("utf-8"))

    def log_message(self, format, *args):
        pass


def _run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    logger.info("وب‌سرور سلامت روی پورت %s بالا آمد", port)
    server.serve_forever()


BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BALE_BOT_TOKEN تنظیم نشده است.")

STEP_TIMEOUT_SECONDS = 15 * 60

bot = bale.Bot(token=BOT_TOKEN)

active_conversations: set[int] = set()


def extract_file(message: "bale.Message"):
    """خروجی: (file_id, file_kind, mime_type یا None, original_filename یا None)"""
    if message.document is not None:
        doc = message.document
        return doc.file_id, "document", getattr(doc, "mime_type", None), getattr(doc, "file_name", None)
    if message.photos:
        photo = message.photos[-1]
        return photo.file_id, "photo", "image/jpeg", None
    return None, None, None, None


async def ask_and_wait_text(message: "bale.Message", question: str) -> str:
    await message.reply(question)

    def check(reply_msg: "bale.Message") -> bool:
        return (
            reply_msg.chat_id == message.chat_id
            and reply_msg.author is not None
            and message.author is not None
            and reply_msg.author.user_id == message.author.user_id
            and reply_msg.text is not None
            and reply_msg.text.strip() != ""
        )

    reply_msg = await bot.wait_for("message", check=check, timeout=STEP_TIMEOUT_SECONDS)
    return reply_msg.text.strip()


@bot.event
async def on_before_ready():
    await bot.delete_webhook()
    init_db()
    logger.info("دیتابیس آماده است.")


@bot.event
async def on_ready():
    logger.info("ربات با موفقیت روشن شد: %s", bot.user)


@bot.event
async def on_message(message: "bale.Message"):
    if message.author is None:
        return

    if message.chat_id in active_conversations:
        return

    if message.text and message.text.strip() in ("/start", "شروع"):
        await message.reply(
            "سلام 👋\n"
            "برای ثبت بازتاب خبری، لطفاً فایل PDF یا عکسِ صفحه روزنامه را همینجا ارسال کنید.\n"
            "بعد از آن، چند سوال کوتاه از شما پرسیده می‌شود."
        )
        return

    file_id, file_kind, mime_type, original_filename = extract_file(message)
    if not file_id:
        if message.text:
            await message.reply(
                "برای شروع ثبت خبر، لطفاً ابتدا فایل PDF یا عکس صفحه روزنامه را ارسال کنید."
            )
        return

    active_conversations.add(message.chat_id)
    try:
        await message.reply("فایل دریافت شد ✅ حالا چند سوال کوتاه می‌پرسم.")

        file_bytes = None
        try:
            file_info = await bot.get_file(file_id)
            file_obj = await bot.download_file(file_info.file_path)
            file_bytes = file_obj.read()
        except Exception:
            logger.exception("خطا در دانلود فایل از بله")

        if not mime_type:
            mime_type = "application/pdf" if file_kind == "document" else "image/jpeg"

        newspaper_name = await ask_and_wait_text(message, "۱) نام روزنامه را وارد کنید:")
        journalist_name = await ask_and_wait_text(message, "۲) نام و نام خانوادگی خبرنگار را وارد کنید:")
        headline = await ask_and_wait_text(message, "۳) تیتر خبر را وارد کنید:")
        publish_date = await ask_and_wait_text(
            message, "۴) تاریخ چاپ را وارد کنید (مثلاً ۱۴۰۴/۰۶/۲۵):"
        )

        session = get_session()
        try:
            submission = Submission(
                newspaper_name=newspaper_name,
                journalist_name=journalist_name,
                headline=headline,
                publish_date=publish_date,
                file_id=file_id,
                file_kind=file_kind,
                file_data=file_bytes,
                file_mimetype=mime_type,
                original_filename=original_filename,
                bale_user_id=str(message.author.user_id),
                bale_chat_id=str(message.chat_id),
                auto_score=compute_auto_score(),
            )
            session.add(submission)
            session.commit()
            session.refresh(submission)
        finally:
            session.close()

        await message.reply(
            "خبر شما با موفقیت ثبت شد. متشکریم! 🙏\n"
            f"روزنامه: {newspaper_name}\n"
            f"تیتر: {headline}\n"
            f"تاریخ: {publish_date}\n"
            f"امتیاز اولیه ثبت‌شده: {submission.auto_score}\n"
            "(امتیاز نهایی پس از بررسی توسط روابط عمومی مشخص می‌شود.)"
        )

    except asyncio.TimeoutError:
        await message.reply(
            "زمان پاسخ‌دهی به پایان رسید و ثبت این خبر لغو شد. "
            "لطفاً فایل را دوباره ارسال کنید تا از ابتدا شروع کنیم."
        )
    except Exception:
        logger.exception("خطا در ثبت ارسال خبرنگار")
        await message.reply(
            "متاسفانه در ثبت این خبر مشکلی پیش آمد. لطفاً دوباره تلاش کنید یا با روابط عمومی تماس بگیرید."
        )
    finally:
        active_conversations.discard(message.chat_id)


if __name__ == "__main__":
    threading.Thread(target=_run_health_check_server, daemon=True).start()
    bot.run()
