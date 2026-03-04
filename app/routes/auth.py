from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from urllib.parse import urlparse, urljoin

from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def is_safe_url(target: str) -> bool:
    """Prevent open-redirect attacks."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


# -------------------------
# Login
# -------------------------
@auth_bp.get("/login", endpoint="login")
def login_get():
    return render_template("auth/login.html")


@auth_bp.post("/login", endpoint="login_post")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        flash("Email and password are required.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        flash("Invalid email or password.", "danger")
        return redirect(url_for("auth.login"))

    login_user(user)

    # Support ?next=/some/protected/page safely
    next_url = request.args.get("next")
    if next_url and is_safe_url(next_url):
        return redirect(next_url)

    flash("Logged in successfully.", "success")
    return redirect(url_for("dash.dashboard"))


# -------------------------
# Register
# -------------------------
@auth_bp.get("/register", endpoint="register")
def register_get():
    return render_template("auth/register.html")


@auth_bp.post("/register", endpoint="register_post")
def register_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        flash("Email and password are required.", "danger")
        return redirect(url_for("auth.register"))

    if User.query.filter_by(email=email).first():
        flash("Email already registered.", "warning")
        return redirect(url_for("auth.register"))

    user = User(email=email)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    flash("Account created. Please log in.", "success")
    return redirect(url_for("auth.login"))


# -------------------------
# Logout
# -------------------------
@auth_bp.post("/logout", endpoint="logout")
@login_required
def logout_post():
    logout_user()
    flash("Logged out.", "success")
    return redirect(url_for("dash.home"))
