from __future__ import annotations

import os
from datetime import datetime, date
from functools import wraps

from flask import Blueprint, jsonify, request, url_for
from flask_login import current_user
from werkzeug.exceptions import Unauthorized, Forbidden, NotFound, BadRequest

from app import db, limiter
from app.models import MealEntry, MacroGoal

api_bp = Blueprint("api", __name__, url_prefix="/api")

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


# -----------------------
# API Auth (either logged-in session OR X-API-KEY header)
# -----------------------
def api_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(current_user, "is_authenticated", False):
            return fn(*args, **kwargs)

        configured_key = os.getenv("API_KEY", "").strip()
        provided_key = (request.headers.get("X-API-KEY") or "").strip()

        if configured_key and provided_key and provided_key == configured_key:
            return fn(*args, **kwargs)

        raise Unauthorized("Unauthorized: login or provide X-API-KEY")

    return wrapper


# -----------------------
# JSON Error Handlers
# -----------------------
@api_bp.errorhandler(Unauthorized)
def handle_unauthorized(e):
    return jsonify({"error": "unauthorized", "message": str(e)}), 401


@api_bp.errorhandler(Forbidden)
def handle_forbidden(e):
    return jsonify({"error": "forbidden", "message": str(e)}), 403


@api_bp.errorhandler(NotFound)
def handle_not_found(e):
    return jsonify({"error": "not_found", "message": str(e)}), 404


@api_bp.errorhandler(BadRequest)
def handle_bad_request(e):
    return jsonify({"error": "bad_request", "message": str(e)}), 400


# -----------------------
# Helpers
# -----------------------
def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_int(x) -> int:
    try:
        if x is None or x == "":
            return 0
        return max(0, int(float(x)))
    except (ValueError, TypeError):
        return 0


def _to_float(x) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return max(0.0, float(x))
    except (ValueError, TypeError):
        return 0.0


def _pct(total: float, target: float) -> int:
    if target <= 0:
        return 0
    return int(round(min(100, (total / target) * 100)))


def _get_or_create_goal(user_id: int) -> MacroGoal:
    goal = MacroGoal.query.filter_by(user_id=user_id).first()
    if goal:
        return goal
    goal = MacroGoal(user_id=user_id)
    db.session.add(goal)
    db.session.commit()
    return goal


def _entry_to_dict(e: MealEntry) -> dict:
    return {
        "id": e.id,
        "entry_date": e.entry_date.strftime("%Y-%m-%d"),
        "meal_type": e.meal_type,
        "food_name": e.food_name,
        "calories": int(e.calories or 0),
        "protein_g": float(e.protein_g or 0),
        "carbs_g": float(e.carbs_g or 0),
        "fat_g": float(e.fat_g or 0),
        "created_at": e.created_at.isoformat() if getattr(e, "created_at", None) else None,
        "links": {
            "self": url_for("api.api_meals_get_one", entry_id=e.id),
            "update": url_for("api.api_meals_update", entry_id=e.id),
            "delete": url_for("api.api_meals_delete", entry_id=e.id),
            "ui_edit": url_for("meals.edit_get", entry_id=e.id),
            "ui_delete": url_for("meals.delete_post", entry_id=e.id),
        },
    }


def _get_user_id() -> int:
    if getattr(current_user, "is_authenticated", False):
        return int(current_user.id)

    data = request.get_json(silent=True) or {}
    raw = request.args.get("user_id") or data.get("user_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise Unauthorized("Missing user_id for API-key request")


def _get_owned_entry_or_404(entry_id: int, user_id: int) -> MealEntry:
    entry = MealEntry.query.get(entry_id)
    if not entry:
        raise NotFound("Meal entry not found")
    if entry.user_id != user_id:
        raise Forbidden("You do not have access to this meal entry")
    return entry


def _require_json():
    if request.is_json:
        return
    raise BadRequest("Expected application/json request body")


def _macro_cals(protein_g: float, carbs_g: float, fat_g: float) -> int:
    """
    Macro calories using 4/4/9 rule:
    protein = 4 kcal/g, carbs = 4 kcal/g, fat = 9 kcal/g
    """
    return int(round((protein_g or 0) * 4 + (carbs_g or 0) * 4 + (fat_g or 0) * 9))


# -----------------------
# GET: Meals for a day
# -----------------------
@api_bp.get("/meals/day")
@limiter.limit("60 per minute")
@api_auth_required
def api_meals_day():
    user_id = _get_user_id()
    selected = _parse_date(request.args.get("date")) or date.today()

    entries = (
        MealEntry.query.filter(MealEntry.user_id == user_id, MealEntry.entry_date == selected)
        .order_by(MealEntry.created_at.desc())
        .all()
    )

    totals = (
        db.session.query(
            db.func.coalesce(db.func.sum(MealEntry.calories), 0),
            db.func.coalesce(db.func.sum(MealEntry.protein_g), 0),
            db.func.coalesce(db.func.sum(MealEntry.carbs_g), 0),
            db.func.coalesce(db.func.sum(MealEntry.fat_g), 0),
        )
        .filter(MealEntry.user_id == user_id, MealEntry.entry_date == selected)
        .one()
    )

    total_cal = int(totals[0] or 0)
    total_p = float(totals[1] or 0)
    total_c = float(totals[2] or 0)
    total_f = float(totals[3] or 0)

    goal = _get_or_create_goal(user_id)

    remaining_cal = max(0, int(goal.calories_target or 0) - total_cal)
    remaining_p = max(0.0, float(goal.protein_target_g or 0) - total_p)
    remaining_c = max(0.0, float(goal.carbs_target_g or 0) - total_c)
    remaining_f = max(0.0, float(goal.fat_target_g or 0) - total_f)

    return jsonify(
        {
            "date": selected.strftime("%Y-%m-%d"),
            "user_id": user_id,
            "entries": [_entry_to_dict(e) for e in entries],
            "totals": {"calories": total_cal, "protein_g": total_p, "carbs_g": total_c, "fat_g": total_f},
            "goals": {
                "calories_target": int(goal.calories_target or 0),
                "protein_target_g": float(goal.protein_target_g or 0),
                "carbs_target_g": float(goal.carbs_target_g or 0),
                "fat_target_g": float(goal.fat_target_g or 0),
            },
            "remaining": {
                "calories": remaining_cal,
                "protein_g": remaining_p,
                "carbs_g": remaining_c,
                "fat_g": remaining_f,
            },
            "progress_pct": {
                "calories": _pct(total_cal, float(goal.calories_target or 0)),
                "protein_g": _pct(total_p, float(goal.protein_target_g or 0)),
                "carbs_g": _pct(total_c, float(goal.carbs_target_g or 0)),
                "fat_g": _pct(total_f, float(goal.fat_target_g or 0)),
            },
        }
    ), 200


# -----------------------
# GET: Single entry
# -----------------------
@api_bp.get("/meals/<int:entry_id>")
@limiter.limit("120 per minute")
@api_auth_required
def api_meals_get_one(entry_id: int):
    user_id = _get_user_id()
    entry = _get_owned_entry_or_404(entry_id, user_id)
    return jsonify({"entry": _entry_to_dict(entry)}), 200


# -----------------------
# POST: Create
# -----------------------
@api_bp.post("/meals")
@limiter.limit("30 per minute")
@api_auth_required
def api_meals_create():
    _require_json()
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}

    entry_date = _parse_date(data.get("entry_date")) or date.today()
    meal_type = (data.get("meal_type") or "").strip().lower()
    food_name = (data.get("food_name") or "").strip()

    if meal_type not in MEAL_TYPES:
        meal_type = "lunch"
    if not food_name:
        raise BadRequest("food_name is required")

    entry = MealEntry(
        user_id=user_id,
        entry_date=entry_date,
        meal_type=meal_type,
        food_name=food_name,
        calories=_to_int(data.get("calories")),
        protein_g=_to_float(data.get("protein_g")),
        carbs_g=_to_float(data.get("carbs_g")),
        fat_g=_to_float(data.get("fat_g")),
    )

    db.session.add(entry)
    db.session.commit()
    return jsonify({"message": "created", "entry": _entry_to_dict(entry)}), 201


# -----------------------
# PUT: Update (partial supported)
# -----------------------
@api_bp.put("/meals/<int:entry_id>")
@limiter.limit("30 per minute")
@api_auth_required
def api_meals_update(entry_id: int):
    _require_json()
    user_id = _get_user_id()
    entry = _get_owned_entry_or_404(entry_id, user_id)
    data = request.get_json(silent=True) or {}

    if "entry_date" in data:
        parsed = _parse_date(data.get("entry_date"))
        if not parsed:
            raise BadRequest("entry_date must be YYYY-MM-DD")
        entry.entry_date = parsed

    if "meal_type" in data:
        mt = (data.get("meal_type") or "").strip().lower()
        if mt and mt not in MEAL_TYPES:
            raise BadRequest(f"meal_type must be one of {MEAL_TYPES}")
        if mt:
            entry.meal_type = mt

    if "food_name" in data:
        fn = (data.get("food_name") or "").strip()
        if not fn:
            raise BadRequest("food_name cannot be empty")
        entry.food_name = fn

    if "calories" in data:
        entry.calories = _to_int(data.get("calories"))
    if "protein_g" in data:
        entry.protein_g = _to_float(data.get("protein_g"))
    if "carbs_g" in data:
        entry.carbs_g = _to_float(data.get("carbs_g"))
    if "fat_g" in data:
        entry.fat_g = _to_float(data.get("fat_g"))

    db.session.commit()
    return jsonify({"message": "updated", "entry": _entry_to_dict(entry)}), 200


# -----------------------
# DELETE
# -----------------------
@api_bp.delete("/meals/<int:entry_id>")
@limiter.limit("20 per minute")
@api_auth_required
def api_meals_delete(entry_id: int):
    user_id = _get_user_id()
    entry = _get_owned_entry_or_404(entry_id, user_id)

    db.session.delete(entry)
    db.session.commit()
    return jsonify({"message": "deleted", "id": entry_id}), 200


# ============================================================
# MACROS API (Goals + Day Summary with 4/4/9 macro calories)
# ============================================================

def _goal_to_dict(goal: MacroGoal) -> dict:
    return {
        "calories_target": int(goal.calories_target or 0),
        "protein_target_g": float(goal.protein_target_g or 0),
        "carbs_target_g": float(goal.carbs_target_g or 0),
        "fat_target_g": float(goal.fat_target_g or 0),
        "macro_calories_target": _macro_cals(
            float(goal.protein_target_g or 0),
            float(goal.carbs_target_g or 0),
            float(goal.fat_target_g or 0),
        ),
        "updated_at": goal.updated_at.isoformat() if getattr(goal, "updated_at", None) else None,
    }


@api_bp.get("/macros/goal")
@limiter.limit("120 per minute")
@api_auth_required
def api_macros_goal_get():
    """
    Get macro targets for the user (creates a goal row if missing).
    """
    user_id = _get_user_id()
    goal = _get_or_create_goal(user_id)
    return jsonify({"user_id": user_id, "goal": _goal_to_dict(goal)}), 200


@api_bp.put("/macros/goal")
@limiter.limit("30 per minute")
@api_auth_required
def api_macros_goal_put():
    """
    Update macro targets (partial update supported).
    Accepts: calories_target, protein_target_g, carbs_target_g, fat_target_g
    Rejects negative values.
    """
    _require_json()
    user_id = _get_user_id()
    goal = _get_or_create_goal(user_id)
    data = request.get_json(silent=True) or {}

    # Validate negatives explicitly (better than silently clamping)
    for k in ["calories_target", "protein_target_g", "carbs_target_g", "fat_target_g"]:
        if k in data:
            try:
                v = float(data.get(k))
            except (TypeError, ValueError):
                raise BadRequest(f"{k} must be a number")
            if v < 0:
                raise BadRequest(f"{k} cannot be negative")

    if "calories_target" in data:
        goal.calories_target = _to_int(data.get("calories_target"))
    if "protein_target_g" in data:
        goal.protein_target_g = _to_float(data.get("protein_target_g"))
    if "carbs_target_g" in data:
        goal.carbs_target_g = _to_float(data.get("carbs_target_g"))
    if "fat_target_g" in data:
        goal.fat_target_g = _to_float(data.get("fat_target_g"))

    db.session.commit()
    return jsonify({"message": "updated", "user_id": user_id, "goal": _goal_to_dict(goal)}), 200


@api_bp.get("/macros/day")
@limiter.limit("60 per minute")
@api_auth_required
def api_macros_day():
    """
    Day summary: totals + goals + remaining + macro calories (4/4/9).
    This mirrors /api/meals/day but includes macro calorie calculation.
    """
    user_id = _get_user_id()
    selected = _parse_date(request.args.get("date")) or date.today()

    totals = (
        db.session.query(
            db.func.coalesce(db.func.sum(MealEntry.calories), 0),
            db.func.coalesce(db.func.sum(MealEntry.protein_g), 0),
            db.func.coalesce(db.func.sum(MealEntry.carbs_g), 0),
            db.func.coalesce(db.func.sum(MealEntry.fat_g), 0),
        )
        .filter(MealEntry.user_id == user_id, MealEntry.entry_date == selected)
        .one()
    )

    total_cal = int(totals[0] or 0)
    total_p = float(totals[1] or 0)
    total_c = float(totals[2] or 0)
    total_f = float(totals[3] or 0)

    macro_cals_total = _macro_cals(total_p, total_c, total_f)

    goal = _get_or_create_goal(user_id)
    goal_dict = _goal_to_dict(goal)
    macro_cals_target = int(goal_dict["macro_calories_target"] or 0)

    remaining = {
        "calories": max(0, int(goal.calories_target or 0) - total_cal),
        "protein_g": max(0.0, float(goal.protein_target_g or 0) - total_p),
        "carbs_g": max(0.0, float(goal.carbs_target_g or 0) - total_c),
        "fat_g": max(0.0, float(goal.fat_target_g or 0) - total_f),
        "macro_calories": max(0, macro_cals_target - macro_cals_total) if macro_cals_target > 0 else 0,
    }

    return jsonify(
        {
            "date": selected.strftime("%Y-%m-%d"),
            "user_id": user_id,
            "totals": {
                "calories": total_cal,
                "protein_g": total_p,
                "carbs_g": total_c,
                "fat_g": total_f,
                "macro_calories_449": macro_cals_total,
            },
            "goals": goal_dict,
            "remaining": remaining,
            "progress_pct": {
                "calories": _pct(total_cal, float(goal.calories_target or 0)),
                "protein_g": _pct(total_p, float(goal.protein_target_g or 0)),
                "carbs_g": _pct(total_c, float(goal.carbs_target_g or 0)),
                "fat_g": _pct(total_f, float(goal.fat_target_g or 0)),
                "macro_calories": _pct(float(macro_cals_total), float(macro_cals_target or 0)),
            },
        }
    ), 200