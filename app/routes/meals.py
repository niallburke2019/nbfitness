# app/routes/meals.py
from datetime import date as date_cls, datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app import db
from app.models import MealEntry, MacroGoal

meals_bp = Blueprint("meals", __name__, url_prefix="/meals")

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


def _parse_date(date_str: str):
    if not date_str:
        return date_cls.today()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date_cls.today()


# -----------------------
# DAY VIEW
# -----------------------
@meals_bp.get("/", endpoint="day_view")
@meals_bp.get("/day", endpoint="day_view_alt")
@meals_bp.get("/day/<date>", endpoint="day_view_date")
@login_required
def day_view(date=None):
    selected_date = _parse_date(date or request.args.get("date"))

    entries = (
        db.session.query(MealEntry)
        .filter(MealEntry.user_id == current_user.id, MealEntry.entry_date == selected_date)
        .order_by(MealEntry.meal_type.asc(), MealEntry.created_at.asc())
        .all()
    )

    goal = (
        db.session.query(MacroGoal)
        .filter(MacroGoal.user_id == current_user.id)
        .first()
    )

    totals = {
        "calories": sum(e.calories or 0 for e in entries),
        "protein_g": sum(e.protein_g or 0 for e in entries),
        "carbs_g": sum(e.carbs_g or 0 for e in entries),
        "fat_g": sum(e.fat_g or 0 for e in entries),
    }

    # 7-day trend (including selected day going back 6 days)
    trend_days = [selected_date - timedelta(days=i) for i in range(6, -1, -1)]
    trend_labels = [d.strftime("%d %b") for d in trend_days]

    trend_cal, trend_p, trend_c, trend_f = [], [], [], []
    for d in trend_days:
        day_entries = (
            db.session.query(MealEntry)
            .filter(MealEntry.user_id == current_user.id, MealEntry.entry_date == d)
            .all()
        )
        trend_cal.append(sum(e.calories or 0 for e in day_entries))
        trend_p.append(float(sum(e.protein_g or 0 for e in day_entries)))
        trend_c.append(float(sum(e.carbs_g or 0 for e in day_entries)))
        trend_f.append(float(sum(e.fat_g or 0 for e in day_entries)))

    # remaining vs goal (safe if no goal row)
    cal_goal = int(goal.calories_target) if goal else 0
    p_goal = float(goal.protein_target_g) if goal else 0.0
    c_goal = float(goal.carbs_target_g) if goal else 0.0
    f_goal = float(goal.fat_target_g) if goal else 0.0

    remaining_cal = max(cal_goal - totals["calories"], 0) if cal_goal else 0
    remaining_p = max(p_goal - totals["protein_g"], 0) if p_goal else 0
    remaining_c = max(c_goal - totals["carbs_g"], 0) if c_goal else 0
    remaining_f = max(f_goal - totals["fat_g"], 0) if f_goal else 0

    return render_template(
        "meals/day.html",
        selected_date=selected_date,
        entries=entries,
        totals=totals,
        goal=goal,
        meal_types=MEAL_TYPES,
        total_cal=totals["calories"],
        total_p=totals["protein_g"],
        total_c=totals["carbs_g"],
        total_f=totals["fat_g"],
        remaining_cal=remaining_cal,
        remaining_p=remaining_p,
        remaining_c=remaining_c,
        remaining_f=remaining_f,
        trend_labels=trend_labels,
        trend_cal=trend_cal,
        trend_p=trend_p,
        trend_c=trend_c,
        trend_f=trend_f,
    )


# -----------------------
# ADD ENTRY
# -----------------------
@meals_bp.get("/add", endpoint="add_get")
@login_required
def add_get():
    day = _parse_date(request.args.get("date"))
    return render_template("meals/add.html", day=day, meal_types=MEAL_TYPES)


@meals_bp.post("/add", endpoint="add_post")
@login_required
def add_post():
    day = _parse_date(request.form.get("entry_date"))

    meal_type = (request.form.get("meal_type") or "breakfast").strip().lower()
    if meal_type not in MEAL_TYPES:
        meal_type = "breakfast"

    food_name = (request.form.get("food_name") or "").strip()
    if not food_name:
        flash("Food name is required.", "warning")
        return redirect(url_for("meals.add_get", date=day.strftime("%Y-%m-%d")))

    entry = MealEntry(
        user_id=current_user.id,
        entry_date=day,
        meal_type=meal_type,
        food_name=food_name,
        calories=int(request.form.get("calories") or 0),
        protein_g=float(request.form.get("protein_g") or 0),
        carbs_g=float(request.form.get("carbs_g") or 0),
        fat_g=float(request.form.get("fat_g") or 0),
    )

    db.session.add(entry)
    db.session.commit()

    flash("Food entry added.", "success")
    return redirect(url_for("meals.day_view", date=day.strftime("%Y-%m-%d")))


# -----------------------
# EDIT ENTRY
# -----------------------
@meals_bp.get("/edit/<int:entry_id>", endpoint="edit_get")
@login_required
def edit_get(entry_id: int):
    entry = db.session.get(MealEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        abort(404)

    return render_template("meals/edit.html", entry=entry, meal_types=MEAL_TYPES)


@meals_bp.post("/edit/<int:entry_id>", endpoint="edit_post")
@login_required
def edit_post(entry_id: int):
    entry = db.session.get(MealEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        abort(404)

    meal_type = (request.form.get("meal_type") or entry.meal_type or "breakfast").strip().lower()
    if meal_type not in MEAL_TYPES:
        meal_type = entry.meal_type or "breakfast"

    entry.meal_type = meal_type
    entry.food_name = (request.form.get("food_name") or "").strip()
    entry.calories = int(request.form.get("calories") or 0)
    entry.protein_g = float(request.form.get("protein_g") or 0)
    entry.carbs_g = float(request.form.get("carbs_g") or 0)
    entry.fat_g = float(request.form.get("fat_g") or 0)

    if not entry.food_name:
        flash("Food name is required.", "warning")
        return redirect(url_for("meals.edit_get", entry_id=entry_id))

    db.session.commit()
    flash("Food entry updated.", "success")
    return redirect(url_for("meals.day_view", date=entry.entry_date.strftime("%Y-%m-%d")))


# -----------------------
# DELETE ENTRY
# -----------------------
@meals_bp.post("/delete/<int:entry_id>", endpoint="delete_post")
@login_required
def delete_post(entry_id: int):
    entry = db.session.get(MealEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        abort(404)

    day = entry.entry_date
    db.session.delete(entry)
    db.session.commit()

    flash("Food entry deleted.", "success")
    return redirect(url_for("meals.day_view", date=day.strftime("%Y-%m-%d")))


# -----------------------
# MACRO GOALS
# -----------------------
@meals_bp.get("/goals", endpoint="goals_get")
@login_required
def goals_get():
    goal = (
        db.session.query(MacroGoal)
        .filter(MacroGoal.user_id == current_user.id)
        .first()
    )
    return render_template("meals/goals.html", goal=goal)


@meals_bp.post("/goals", endpoint="goals_post")
@login_required
def goals_post():
    goal = (
        db.session.query(MacroGoal)
        .filter(MacroGoal.user_id == current_user.id)
        .first()
    )

    if not goal:
        goal = MacroGoal(user_id=current_user.id)
        db.session.add(goal)

    goal.calories_target = int(request.form.get("calories_target") or 0)
    goal.protein_target_g = float(request.form.get("protein_target_g") or 0)
    goal.carbs_target_g = float(request.form.get("carbs_target_g") or 0)
    goal.fat_target_g = float(request.form.get("fat_target_g") or 0)

    db.session.commit()
    flash("Macro goals saved.", "success")
    return redirect(url_for("meals.goals_get"))


# -----------------------
# HISTORY (Last 30 days)
# -----------------------
@meals_bp.get("/history", endpoint="history")
@login_required
def history():
    today = date_cls.today()
    start = today - timedelta(days=29)

    entries = (
        db.session.query(MealEntry)
        .filter(
            MealEntry.user_id == current_user.id,
            MealEntry.entry_date >= start,
            MealEntry.entry_date <= today,
        )
        .order_by(MealEntry.entry_date.desc(), MealEntry.meal_type.asc(), MealEntry.created_at.desc())
        .all()
    )

    goal = (
        db.session.query(MacroGoal)
        .filter(MacroGoal.user_id == current_user.id)
        .first()
    )

    return render_template("meals/history.html", entries=entries, goal=goal, start=start, end=today)