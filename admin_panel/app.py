# -*- coding: utf-8 -*-
"""
admin_panel/app.py
-------------------
پنل مدیریت وب برای دیدن خبرهای ارسالی، اصلاح امتیاز (از جمله تایید صفحه اول)،
و گرفتن خروجی اکسل. با نام کاربری/رمز ساده محافظت می‌شود (برای شروع کافی است).
"""
import io
import os
import sys
import datetime
import functools
import mimetypes

import requests
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

# اجازه بده db.py و scoring.py از پوشه‌ی اصلی پروژه import بشن
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Submission, get_session, init_db  # noqa: E402
from scoring import FRONT_PAGE_BONUS_SUGGESTION  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET_KEY", "change-this-secret-key")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_API_BASE = "https://tapi.bale.ai"

init_db()


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
