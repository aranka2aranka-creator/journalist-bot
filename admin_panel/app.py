# -*- coding: utf-8 -*-
"""
admin_panel/app.py
-------------------
پنل مدیریت وب برای دیدن خبرهای ارسالی، اصلاح امتیاز، گرفتن خروجی اکسل و زیپ.
"""
import io
import os
import re
import sys
import datetime
import functools
import mimetypes

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session as flask_session,
    send_file,
    flash,
    Response,
    abort,
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Submission, get_session, init_db  # noqa: E402
from scoring import FRONT_PAGE_BONUS_SUGGESTION  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET_KEY", "change-this-secret-key")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

init_db()


def sanitize_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]', "-", name)
    name = re.sub(r"\s+", " ", name)
    return name[:120] or "بدون-عنوان"


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not flask_session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and ADMIN_PASSWORD and password == ADMIN_PASSWORD:
            flask_session["logged_in"] = True
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("نام کاربری یا رمز عبور اشتباه است.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    db = get_session()
    try:
        newspaper_filter = request.args.get("newspaper", "").strip()
        query = db.query(Submission).order_by(Submission.created_at.desc())
        if newspaper_filter:
            query = query.filter(Submission.newspaper_name == newspaper_filter)
        submissions = query.all()

        totals: dict[str, int] = {}
        for s in db.query(Submission).all():
            totals[s.newspaper_name] = totals.get(s.newspaper_name, 0) + s.effective_score
        totals_sorted = sorted(totals.items(), key=lambda x: x[1], reverse=True)

        newspapers = sorted({s.newspaper_name for s in db.query(Submission).all()})

        return render_template(
            "index.html",
            submissions=submissions,
            totals=totals_sorted,
            newspapers=newspapers,
            active_filter=newspaper_filter,
        )
    finally:
        db.close()


@app.route("/submission/<int:submission_id>/update", methods=["POST"])
@login_required
def update_submission(submission_id):
    db = get_session()
    try:
        submission = db.query(Submission).get(submission_id)
        if submission is None:
            flash("این ارسال پیدا نشد.")
            return redirect(url_for("index"))

        is_front_page = request.form.get("is_front_page")
        final_score = request.form.get("final_score", "").strip()
        admin_note = request.form.get("admin_note", "").strip()

        submission.is_front_page = True if is_front_page == "yes" else (
            False if is_front_page == "no" else None
        )
        submission.final_score = int(final_score) if final_score else None
        submission.admin_note = admin_note or None
        submission.reviewed_at = datetime.datetime.utcnow()

        db.commit()
        flash("امتیاز با موفقیت ذخیره شد.")
    finally:
        db.close()
    return redirect(url_for("index"))


@app.route("/submission/<int:submission_id>/file")
@login_required
def download_file(submission_id):
    db = get_session()
    try:
        submission = db.query(Submission).get(submission_id)
        if submission is None:
            abort(404)
        if not submission.file_data:
            abort(404, "فایلی برای این رکورد ذخیره نشده.")

        mimetype = submission.file_mimetype or "application/octet-stream"
        extension = os.path.splitext(submission.original_filename or "")[1]
        if not extension:
            extension = mimetypes.guess_extension(mimetype) or (
                ".jpg" if submission.file_kind == "photo" else ".pdf"
            )
        download_name = f"{submission.newspaper_name}-{submission_id}{extension}"
        file_bytes = submission.file_data
    finally:
        db.close()

    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=False,
        download_name=download_name,
        mimetype=mimetype,
    )


@app.route("/submission/<int:submission_id>/delete", methods=["POST"])
@login_required
def delete_submission(submission_id):
    db = get_session()
    try:
        submission = db.query(Submission).get(submission_id)
        if submission is None:
            flash("این ارسال پیدا نشد.")
            return redirect(url_for("index"))
        db.delete(submission)
        db.commit()
        flash("رکورد حذف شد.")
    finally:
        db.close()
    return redirect(url_for("index"))


@app.route("/submissions/bulk-delete", methods=["POST"])
@login_required
def bulk_delete():
    ids = request.form.getlist("ids")
    if not ids:
        flash("هیچ موردی انتخاب نشده بود.")
        return redirect(url_for("index"))
    db = get_session()
    try:
        deleted_count = (
            db.query(Submission)
            .filter(Submission.id.in_([int(i) for i in ids]))
            .delete(synchronize_session=False)
        )
        db.commit()
        flash(f"{deleted_count} رکورد حذف شد.")
    finally:
        db.close()
    return redirect(url_for("index"))


@app.route("/export.xlsx")
@login_required
def export_excel():
    import openpyxl
    from openpyxl.utils import get_column_letter

    db = get_session()
    try:
        submissions = db.query(Submission).order_by(Submission.newspaper_name).all()
    finally:
        db.close()

    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "همه اخبار"
    headers = [
        "روزنامه",
        "خبرنگار",
        "تیتر",
        "تاریخ چاپ",
        "صفحه اول",
        "امتیاز اولیه",
        "امتیاز نهایی",
        "یادداشت ادمین",
        "تاریخ ثبت",
    ]
    ws.append(headers)
    for s in submissions:
        ws.append(
            [
                s.newspaper_name,
                s.journalist_name,
                s.headline,
                s.publish_date,
                "بله" if s.is_front_page else ("خیر" if s.is_front_page is False else ""),
                s.auto_score,
                s.final_score if s.final_score is not None else "",
                s.admin_note or "",
                s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
            ]
        )
    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 22

    ws2 = wb.create_sheet("جمع امتیاز روزنامه‌ها")
    ws2.append(["روزنامه", "تعداد خبر", "جمع امتیاز"])
    totals: dict[str, list[int]] = {}
    for s in submissions:
        row = totals.setdefault(s.newspaper_name, [0, 0])
        row[0] += 1
        row[1] += s.effective_score
    for name, (count, total_score) in sorted(totals.items(), key=lambda x: x[1][1], reverse=True):
        ws2.append([name, count, total_score])
    for i in range(1, 4):
        ws2.column_dimensions[get_column_letter(i)].width = 24

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"gozaresh-khabarnegaran-{datetime.date.today().isoformat()}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/export.zip")
@login_required
def export_zip():
    import zipfile

    db = get_session()
    try:
        submissions = db.query(Submission).order_by(Submission.created_at).all()
    finally:
        db.close()

    buffer = io.BytesIO()
    used_names: dict[tuple[str, str], int] = {}

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for s in submissions:
            if not s.file_data:
                continue

            folder = sanitize_name(s.headline)
            base_name = sanitize_name(s.newspaper_name)

            extension = os.path.splitext(s.original_filename or "")[1]
            if not extension:
                extension = mimetypes.guess_extension(s.file_mimetype or "") or (
                    ".jpg" if s.file_kind == "photo" else ".pdf"
                )

            key = (folder, base_name)
            count = used_names.get(key, 0)
            used_names[key] = count + 1
            filename = f"{base_name}{extension}" if count == 0 else f"{base_name}-{count + 1}{extension}"

            zf.writestr(f"{folder}/{filename}", s.file_data)

    buffer.seek(0)
    zip_name = f"tasavir-va-pdf-ha-{datetime.date.today().isoformat()}.zip"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=zip_name,
        mimetype="application/zip",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
