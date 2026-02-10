from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.get("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dash.dashboard"))
    return render_template("auth/register.html")

@auth_bp.post("/register")
def register_post():
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    password = request.form.get("password") or ""

    if not email or not password:
        flash("Email and password are required.", "error")
        return redirect(url_for("auth.register"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("auth.register"))

    if User.query.filter_by(email=email).first():
        flash("An account with that email already exists.", "error")
        return redirect(url_for("auth.register"))

    user = User(email=email, name=name if name else None)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    flash("Account created. Please log in.", "success")
    return redirect(url_for("auth.login"))

@auth_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dash.dashboard"))
    return render_template("auth/login.html")

@auth_bp.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("auth.login"))

    login_user(user)
    flash("Logged in successfully.", "success")
    return redirect(url_for("dash.dashboard"))

@auth_bp.get("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
