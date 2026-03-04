from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user, logout_user

from app import db
from app.models import User

account_bp = Blueprint("account", __name__, url_prefix="/account")


@account_bp.get("/")
@login_required
def index():
    return render_template("account/account.html")


@account_bp.post("/password")
@login_required
def change_password_post():
    current_pw = request.form.get("current_password") or ""
    new_pw = request.form.get("new_password") or ""
    confirm_pw = request.form.get("confirm_password") or ""

    # Basic validation
    if not current_pw or not new_pw or not confirm_pw:
        flash("Please fill in all password fields.", "danger")
        return redirect(url_for("account.index"))

    if not current_user.check_password(current_pw):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("account.index"))

    if len(new_pw) < 8:
        flash("New password must be at least 8 characters.", "danger")
        return redirect(url_for("account.index"))

    if new_pw != confirm_pw:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("account.index"))

    if current_user.check_password(new_pw):
        flash("New password must be different from your current password.", "danger")
        return redirect(url_for("account.index"))

    # Update
    user: User = db.session.get(User, int(current_user.get_id()))
    user.set_password(new_pw)
    db.session.commit()

    # Force re-login for safety
    logout_user()
    flash("Password changed successfully. Please log in again.", "success")
    return redirect(url_for("auth.login"))


@account_bp.post("/delete")
@login_required
def delete_account_post():
    """
    Delete account with a strong confirmation:
    - must type email
    - must enter current password
    """
    confirm_email = (request.form.get("confirm_email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not confirm_email or not password:
        flash("Please confirm your email and password to delete your account.", "danger")
        return redirect(url_for("account.index"))

    if confirm_email != (current_user.email or "").lower():
        flash("Email confirmation does not match.", "danger")
        return redirect(url_for("account.index"))

    if not current_user.check_password(password):
        flash("Password is incorrect.", "danger")
        return redirect(url_for("account.index"))

    # Delete the user (cascades should delete workouts/meals/weights etc.)
    user: User = db.session.get(User, int(current_user.get_id()))
    logout_user()
    db.session.delete(user)
    db.session.commit()

    flash("Your account has been deleted.", "warning")
    return redirect(url_for("dash.home"))