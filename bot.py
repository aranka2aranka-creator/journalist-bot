# -*- coding: utf-8 -*-
"""
bot.py
------
ربات بله برای دریافت بازتاب‌های خبری از خبرنگاران.

روند گفتگو با هر خبرنگار:
  ۱. خبرنگار فایل (PDF یا عکس) خبر چاپ‌شده را می‌فرستد
  ۲. ربات نام روزنامه را می‌پرسد
  ۳. ربات نام خبرنگار را می‌پرسد
  ۴. ربات تیتر خبر را می‌پرسد
  ۵. ربات تاریخ را می‌پرسد
  ۶. ربات همه را ذخیره می‌کند، امتیاز اولیه می‌دهد و تایید می‌فرستد

نکته: کتابخانه‌ی python-bale-bot با تلگرام سازگار است و متد wait_for
دقیقاً برای همین نوع گفتگوهای مرحله‌ای طراحی شده.
مستندات: https://docs.python-bale-bot.ir
"""
import asyncio
import logging
import os

import bale

from db import Submission, get_session, init_db
from scoring import compute_auto_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("journalist-bot")

BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BALE_BOT_TOKEN تنظیم نشده است.")

# هر چند ثانیه منتظر پاسخ خبرنگار به هر سوال بماند، قبل از این‌که مکالمه را لغو کند
STEP_TIMEOUT_SECONDS = 15 * 60  # ۱۵ دقیقه

bot = bale.Bot(token=BOT_TOKEN)


def extract_file(message: "bale.Message"):
    """از پیام، شناسه فایل (file_id) و نوع آن (document/photo) را استخراج می‌کند."""
    if message.document is not None:
        return message.document.file_id, "document"
    if message.photos:
        # آخرین آیتم لیست معمولاً بزرگترین سایز عکس است
        return message.photos[-1].file_id, "photo"
    return None, None


async def ask_and_wait_text(message: "bale.Message", question: str) -> str:
    """یک سوال متنی می‌پرسد و منتظر پاسخ متنیِ همان کاربر در همان چت می‌ماند."""
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
    # طبق راهنمای کتابخانه، قبل از هر بار اجرا وبهوک قبلی حذف می‌شود
    await bot.delete_webhook()
    init_db()
    logger.info("دیتابیس آماده است.")


@bot.event
async def on_ready():
    logger.info("ربات با موفقیت روشن شد: %s", bot.user)


@bot.event
async def on_message(message: "bale.Message"):
    # پیام‌هایی که خودِ ربات فرستاده یا فاقد فرستنده هستند نادیده گرفته می‌شوند
    if message.author is None:
        return

    # دستور شروع
    if message.text and message.text.strip() in ("/start", "شروع"):
        await message.reply(
            "سلام 👋\n"
            "برای ثبت بازتاب خبری، لطفاً فایل PDF یا عکسِ صفحه روزنامه را همینجا ارسال کنید.\n"
            "بعد از آن، چند سوال کوتاه از شما پرسیده می‌شود."
        )
        return

    file_id, file_kind = extract_file(message)
    if not file_id:
        # پیامی که نه فایل است و نه دستور /start؛ فقط راهنمایی می‌کنیم
        if message.text:
            await message.reply(
                "برای شروع ثبت خبر، لطفاً ابتدا فایل PDF یا عکس صفحه روزنامه را ارسال کنید."
            )
        return

    try:
        await message.reply("فایل دریافت شد ✅ حالا چند سوال کوتاه می‌پرسم.")

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


if __name__ == "__main__":
    bot.run()
