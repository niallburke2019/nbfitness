from __future__ import annotations

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app import db
from app.models import Workout, WorkoutExercise, WorkoutSet

workouts_bp = Blueprint("workouts", __name__)


# -----------------------
# helpers
# -----------------------
def _get_workout_or_404(workout_id: int) -> Workout:
    w = Workout.query.get_or_404(workout_id)
    if w.user_id != current_user.id:
        abort(403)
    return w


def _parse_exercise_lines(text: str) -> list[dict]:
    """
    Format (one per line):
      Exercise Name | weight | reps | sets
    Example:
      Bench Press | 80 | 8 | 3
      Incline DB Press | 30 | 10 | 3
      Lat Pulldown | 55 | 12 | 3

    - weight/reps/sets optional (blank allowed)
    - sets defaults to 1 if weight+reps present
    """
    items: list[dict] = []
    if not text:
        return items

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]
        name = parts[0] if len(parts) >= 1 else ""
        if not name:
            continue

        weight = None
        reps = None
        sets_count = 0

        if len(parts) >= 2 and parts[1]:
            try:
                weight = float(parts[1])
            except ValueError:
                weight = None

        if len(parts) >= 3 and parts[2]:
            try:
                reps = int(parts[2])
            except ValueError:
                reps = None

        if len(parts) >= 4 and parts[3]:
            try:
                sets_count = int(parts[3])
            except ValueError:
                sets_count = 0

        # If user provided weight+reps but no sets, assume 1 set
        if sets_count <= 0 and (weight is not None or reps is not None):
            sets_count = 1

        items.append(
            {
                "name": name,
                "weight": weight,
                "reps": reps,
                "sets_count": sets_count,
            }
        )

    return items


def _apply_exercises_to_workout(workout: Workout, exercise_lines: str) -> None:
    """
    Replace workout.exercises with parsed lines.
    """
    workout.exercises.clear()

    parsed = _parse_exercise_lines(exercise_lines)

    for ex_index, item in enumerate(parsed):
        ex = WorkoutExercise(name=item["name"], position=ex_index)
        workout.exercises.append(ex)

        weight = item["weight"]
        reps = item["reps"]
        sets_count = item["sets_count"]

        for set_index in range(sets_count):
            s = WorkoutSet(weight=weight, reps=reps, position=set_index)
            ex.sets.append(s)


# -----------------------
# LIST WORKOUTS (search/filter/sort + pagination)
# -----------------------
@workouts_bp.get("/workouts")
@login_required
def list_workouts():
    q = (request.args.get("q") or "").strip()
    start_raw = (request.args.get("start") or "").strip()
    end_raw = (request.args.get("end") or "").strip()
    sort = (request.args.get("sort") or "date_desc").strip()
    page_raw = (request.args.get("page") or "1").strip()

    # page safe parse
    try:
        page = int(page_raw)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    query = Workout.query.filter(Workout.user_id == current_user.id)

    # title search (case-insensitive)
    if q:
        query = query.filter(Workout.title.ilike(f"%{q}%"))

    # date filters
    if start_raw:
        try:
            start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
            query = query.filter(Workout.workout_date >= start_date)
        except ValueError:
            pass

    if end_raw:
        try:
            end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
            query = query.filter(Workout.workout_date <= end_date)
        except ValueError:
            pass

    # sorting (matches your template)
    if sort == "date_asc":
        query = query.order_by(Workout.workout_date.asc(), Workout.created_at.asc())
    elif sort == "duration_desc":
        query = query.order_by(Workout.duration_minutes.desc(), Workout.workout_date.desc())
    elif sort == "duration_asc":
        query = query.order_by(Workout.duration_minutes.asc(), Workout.workout_date.desc())
    else:
        sort = "date_desc"
        query = query.order_by(Workout.workout_date.desc(), Workout.created_at.desc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template(
        "workouts/list.html",
        workouts=pagination.items,
        pagination=pagination,
        q=q,
        start=start_raw,
        end=end_raw,
        sort=sort,
    )


# -----------------------
# CREATE WORKOUT
# -----------------------
@workouts_bp.get("/workouts/new")
@login_required
def create_workout_get():
    return render_template("workouts/create.html")


@workouts_bp.post("/workouts/new")
@login_required
def create_workout_post():
    title = (request.form.get("title") or "").strip()
    workout_date_raw = (request.form.get("workout_date") or "").strip()
    duration_raw = (request.form.get("duration_minutes") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    exercise_lines = (request.form.get("exercise_lines") or "").strip()

    if not title or not workout_date_raw:
        flash("Title and date are required.", "danger")
        return redirect(url_for("workouts.create_workout_get"))

    try:
        workout_date = datetime.strptime(workout_date_raw, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for("workouts.create_workout_get"))

    try:
        duration = int(duration_raw) if duration_raw else 0
        if duration < 0:
            duration = 0
    except ValueError:
        duration = 0

    workout = Workout(
        title=title,
        workout_date=workout_date,
        duration_minutes=duration,
        notes=notes or None,
        user_id=current_user.id,
    )

    _apply_exercises_to_workout(workout, exercise_lines)

    db.session.add(workout)
    db.session.commit()

    flash("Workout created successfully.", "success")
    return redirect(url_for("workouts.view_workout", workout_id=workout.id))


# -----------------------
# VIEW WORKOUT (DETAIL)
# -----------------------
@workouts_bp.get("/workouts/<int:workout_id>")
@login_required
def view_workout(workout_id: int):
    workout = _get_workout_or_404(workout_id)
    return render_template("workouts/detail.html", workout=workout)


# -----------------------
# EDIT WORKOUT
# -----------------------
@workouts_bp.get("/workouts/<int:workout_id>/edit")
@login_required
def edit_workout_get(workout_id: int):
    workout = _get_workout_or_404(workout_id)

    # Pre-fill exercise_lines from existing data
    lines = []
    for ex in workout.exercises:
        if ex.sets:
            w0 = ex.sets[0].weight
            r0 = ex.sets[0].reps
            identical = all((s.weight == w0 and s.reps == r0) for s in ex.sets)
            if identical:
                lines.append(
                    f"{ex.name} | {w0 if w0 is not None else ''} | {r0 if r0 is not None else ''} | {len(ex.sets)}"
                )
            else:
                lines.append(f"{ex.name}")
        else:
            lines.append(f"{ex.name}")

    exercise_lines = "\n".join(lines)

    return render_template("workouts/edit.html", workout=workout, exercise_lines=exercise_lines)


@workouts_bp.post("/workouts/<int:workout_id>/edit")
@login_required
def edit_workout_post(workout_id: int):
    workout = _get_workout_or_404(workout_id)

    title = (request.form.get("title") or "").strip()
    workout_date_raw = (request.form.get("workout_date") or "").strip()
    duration_raw = (request.form.get("duration_minutes") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    exercise_lines = (request.form.get("exercise_lines") or "").strip()

    if not title or not workout_date_raw:
        flash("Title and date are required.", "danger")
        return redirect(url_for("workouts.edit_workout_get", workout_id=workout_id))

    try:
        workout.workout_date = datetime.strptime(workout_date_raw, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for("workouts.edit_workout_get", workout_id=workout_id))

    try:
        duration = int(duration_raw) if duration_raw else 0
        if duration < 0:
            duration = 0
    except ValueError:
        duration = 0

    workout.title = title
    workout.duration_minutes = duration
    workout.notes = notes or None

    _apply_exercises_to_workout(workout, exercise_lines)

    db.session.commit()

    flash("Workout updated successfully.", "success")
    return redirect(url_for("workouts.view_workout", workout_id=workout.id))


# -----------------------
# DELETE WORKOUT
# -----------------------
@workouts_bp.post("/workouts/<int:workout_id>/delete")
@login_required
def delete_workout_post(workout_id: int):
    workout = _get_workout_or_404(workout_id)
    db.session.delete(workout)
    db.session.commit()
    flash("Workout deleted.", "warning")
    return redirect(url_for("workouts.list_workouts"))
