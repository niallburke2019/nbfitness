from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import Workout, WorkoutExercise, WorkoutSet

workouts_bp = Blueprint("workouts", __name__)


# -----------------------
# LIST WORKOUTS
# -----------------------
@workouts_bp.get("/workouts")
@login_required
def list_workouts():
    workouts = (
        db.session.query(Workout)
        .filter(Workout.user_id == current_user.id)
        .order_by(Workout.workout_date.desc(), Workout.created_at.desc())
        .all()
    )
    return render_template("workouts/list.html", workouts=workouts)


# -----------------------
# CREATE WORKOUT
# -----------------------
@workouts_bp.route("/workouts/new", methods=["GET", "POST"])
@login_required
def create_workout():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        workout_date_raw = (request.form.get("workout_date") or "").strip()
        notes = (request.form.get("notes") or "").strip()

        if not title:
            flash("Workout title is required.", "danger")
            return redirect(url_for("workouts.create_workout"))

        try:
            workout_date = datetime.strptime(workout_date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Please enter a valid workout date.", "danger")
            return redirect(url_for("workouts.create_workout"))

        workout = Workout(
            user_id=current_user.id,
            title=title,
            workout_date=workout_date,
            notes=notes if notes else None,
        )
        db.session.add(workout)
        db.session.commit()

        flash("Workout created.", "success")
        return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    return render_template("workouts/new.html")


# -----------------------
# VIEW WORKOUT
# -----------------------
@workouts_bp.get("/workouts/<int:workout_id>")
@login_required
def view_workout(workout_id):
    workout = db.session.get(Workout, workout_id)
    if not workout or workout.user_id != current_user.id:
        flash("Workout not found.", "warning")
        return redirect(url_for("workouts.list_workouts"))

    return render_template("workouts/view_workout.html", workout=workout)


# -----------------------
# ADD EXERCISE
# -----------------------
@workouts_bp.post("/workouts/<int:workout_id>/exercise/add")
@login_required
def add_exercise(workout_id):
    workout = db.session.get(Workout, workout_id)
    if not workout or workout.user_id != current_user.id:
        flash("Workout not found.", "warning")
        return redirect(url_for("workouts.list_workouts"))

    name = (request.form.get("name") or "").strip()
    muscle_group = (request.form.get("muscle_group") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    if not name:
        flash("Exercise name is required.", "danger")
        return redirect(url_for("workouts.view_workout", workout_id=workout_id))

    exercise = WorkoutExercise(
        workout_id=workout_id,
        name=name,
        muscle_group=muscle_group if muscle_group else None,
        notes=notes if notes else None,
    )
    db.session.add(exercise)
    db.session.commit()

    flash("Exercise added.", "success")
    return redirect(url_for("workouts.view_workout", workout_id=workout_id))


# -----------------------
# ADD SET (SAFE NUMBERING)
# -----------------------
@workouts_bp.post("/workouts/exercise/<int:exercise_id>/set/add")
@login_required
def add_set(exercise_id):
    exercise = db.session.get(WorkoutExercise, exercise_id)
    if not exercise:
        flash("Exercise not found.", "warning")
        return redirect(url_for("workouts.list_workouts"))

    workout = exercise.workout
    if workout.user_id != current_user.id:
        flash("You do not have permission to edit this workout.", "danger")
        return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    reps_raw = (request.form.get("reps") or "").strip()
    weight_raw = (request.form.get("weight_kg") or "").strip()
    rir_raw = (request.form.get("rir") or "").strip()

    # Validate reps
    try:
        reps = int(reps_raw)
        if reps <= 0:
            raise ValueError
    except ValueError:
        flash("Reps must be a positive whole number.", "danger")
        return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    # Validate weight (optional)
    weight_kg = None
    if weight_raw:
        try:
            weight_kg = float(weight_raw)
            if weight_kg < 0:
                raise ValueError
        except ValueError:
            flash("Weight must be a valid number (0 or greater).", "danger")
            return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    # Validate rir (optional)
    rir = None
    if rir_raw:
        try:
            rir = int(rir_raw)
            if rir < 0 or rir > 10:
                raise ValueError
        except ValueError:
            flash("RIR must be a whole number between 0 and 10.", "danger")
            return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    # Safe next set number
    current_max = max([s.set_number for s in exercise.sets], default=0)
    next_set_number = current_max + 1

    workout_set = WorkoutSet(
        exercise_id=exercise_id,
        set_number=next_set_number,
        reps=reps,
        weight_kg=weight_kg,
        rir=rir,
    )
    db.session.add(workout_set)
    db.session.commit()

    flash("Set added.", "success")
    return redirect(url_for("workouts.view_workout", workout_id=workout.id))


# -----------------------
# DELETE SET + RENUMBER
# -----------------------
@workouts_bp.post("/workouts/set/<int:set_id>/delete")
@login_required
def delete_set(set_id):
    workout_set = db.session.get(WorkoutSet, set_id)
    if not workout_set:
        flash("Set not found.", "warning")
        return redirect(url_for("workouts.list_workouts"))

    exercise = workout_set.exercise
    workout = exercise.workout

    if workout.user_id != current_user.id:
        flash("You do not have permission to delete this set.", "danger")
        return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    workout_id = workout.id
    exercise_id = exercise.id

    db.session.delete(workout_set)
    db.session.flush()

    remaining_sets = (
        db.session.query(WorkoutSet)
        .filter(WorkoutSet.exercise_id == exercise_id)
        .order_by(WorkoutSet.set_number.asc(), WorkoutSet.id.asc())
        .all()
    )

    for i, s in enumerate(remaining_sets, start=1):
        s.set_number = i

    db.session.commit()

    flash("Set deleted.", "success")
    return redirect(url_for("workouts.view_workout", workout_id=workout_id))


# -----------------------
# DELETE EXERCISE (POST ONLY) ✅ NOW SIMPLE (cascade handles sets)
# -----------------------
@workouts_bp.post("/workouts/exercise/<int:exercise_id>/delete")
@login_required
def delete_exercise(exercise_id):
    exercise = db.session.get(WorkoutExercise, exercise_id)
    if not exercise:
        flash("Exercise not found.", "warning")
        return redirect(url_for("workouts.list_workouts"))

    workout = exercise.workout
    if workout.user_id != current_user.id:
        flash("You do not have permission to delete this exercise.", "danger")
        return redirect(url_for("workouts.view_workout", workout_id=workout.id))

    workout_id = workout.id

    db.session.delete(exercise)  # ✅ cascade deletes sets
    db.session.commit()

    flash("Exercise deleted.", "success")
    return redirect(url_for("workouts.view_workout", workout_id=workout_id))


# -----------------------
# DELETE WORKOUT (POST ONLY) ✅ NOW SIMPLE (cascade handles exercises + sets)
# -----------------------
@workouts_bp.post("/workouts/<int:workout_id>/delete")
@login_required
def delete_workout(workout_id):
    workout = db.session.get(Workout, workout_id)
    if not workout or workout.user_id != current_user.id:
        flash("Workout not found.", "warning")
        return redirect(url_for("workouts.list_workouts"))

    db.session.delete(workout)  # ✅ cascade deletes exercises + sets
    db.session.commit()

    flash("Workout deleted.", "success")
    return redirect(url_for("workouts.list_workouts"))
