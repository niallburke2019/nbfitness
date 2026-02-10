from flask import Blueprint, render_template
from flask_login import login_required, current_user

dash_bp = Blueprint("dash", __name__)

@dash_bp.get("/")
def home():
    return render_template("dashboard/home.html")

@dash_bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard/dashboard.html", user=current_user)
