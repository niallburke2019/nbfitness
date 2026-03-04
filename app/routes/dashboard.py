from datetime import date, timedelta
import calendar

from flask import Blueprint, render_template, current_app, request
from flask_login import login_required, current_user

from app import db
from app.models import (
    Workout,
    WorkoutExercise,
    WorkoutSet,
    MealEntry,
    WeightEntry,
)

dash_bp = Blueprint("dash", __name__)


@dash_bp.get("/")
def home():
    return render_template("dashboard/home.html")


@dash_bp.get("/dashboard")
@login_required
def dashboard():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())  # Monday

    # ----------------------------
    # WORKOUT SUMMARY
    # ----------------------------
    total_workouts = Workout.query.filter_by(user_id=current_user.id).count()

    workouts_this_week = (
        Workout.query.filter(
            Workout.user_id == current_user.id,
            Workout.workout_date >= start_of_week,
            Workout.workout_date <= today,
        ).count()
    )

    minutes_this_week = (
        db.session.query(db.func.coalesce(db.func.sum(Workout.duration_minutes), 0))
        .filter(
            Workout.user_id == current_user.id,
            Workout.workout_date >= start_of_week,
            Workout.workout_date <= today,
        )
        .scalar()
    )
    minutes_this_week = int(minutes_this_week or 0)

    total_minutes_all_time = (
        db.session.query(db.func.coalesce(db.func.sum(Workout.duration_minutes), 0))
        .filter(Workout.user_id == current_user.id)
        .scalar()
    )
    total_minutes_all_time = int(total_minutes_all_time or 0)

    latest_workouts = (
        Workout.query.filter_by(user_id=current_user.id)
        .order_by(Workout.workout_date.desc(), Workout.created_at.desc())
        .limit(5)
        .all()
    )

    weekly_goal = int(current_app.config.get("WEEKLY_MINUTES_GOAL", 150))
    goal_percent = 0
    if weekly_goal > 0:
        goal_percent = round(min(100, (minutes_this_week / weekly_goal) * 100))

    # ----------------------------
    # MEALS SUMMARY (7-day)
    # ----------------------------
    last7_start = today - timedelta(days=6)

    meal_rows_7d = (
        db.session.query(
            MealEntry.entry_date.label("d"),
            db.func.coalesce(db.func.sum(MealEntry.calories), 0).label("cal"),
        )
        .filter(MealEntry.user_id == current_user.id)
        .filter(MealEntry.entry_date >= last7_start, MealEntry.entry_date <= today)
        .group_by(MealEntry.entry_date)
        .order_by(MealEntry.entry_date.asc())
        .all()
    )

    cal_by_day = {r.d: int(r.cal or 0) for r in meal_rows_7d}

    cal_labels_7d = []
    cal_values_7d = []
    d = last7_start
    while d <= today:
        cal_labels_7d.append(d.strftime("%d %b"))
        cal_values_7d.append(cal_by_day.get(d, 0))
        d += timedelta(days=1)

    avg_calories_7d = int(round(sum(cal_values_7d) / 7)) if cal_values_7d else 0

    # ----------------------------
    # BODYWEIGHT SUMMARY (30-day mini trend)
    # ----------------------------
    weight_end = today
    weight_start = today - timedelta(days=29)

    weight_rows = (
        db.session.query(
            WeightEntry.entry_date.label("d"),
            WeightEntry.weight_kg.label("w"),
        )
        .filter(WeightEntry.user_id == current_user.id)
        .filter(WeightEntry.entry_date >= weight_start, WeightEntry.entry_date <= weight_end)
        .order_by(WeightEntry.entry_date.asc())
        .all()
    )
    weight_by_day = {r.d: float(r.w) for r in weight_rows}

    weight_labels_30d = []
    weight_values_30d = []
    d = weight_start
    while d <= weight_end:
        weight_labels_30d.append(d.strftime("%d %b"))
        weight_values_30d.append(weight_by_day.get(d, None))  # allow gaps
        d += timedelta(days=1)

    latest_weight = (
        WeightEntry.query.filter_by(user_id=current_user.id)
        .order_by(WeightEntry.entry_date.desc())
        .first()
    )

    latest_weight_kg = float(latest_weight.weight_kg) if latest_weight else None
    latest_weight_date = latest_weight.entry_date if latest_weight else None

    # ----------------------------
    # STREAK (any log: meal OR workout OR weight)
    # ----------------------------
    streak_window_start = today - timedelta(days=365)

    workout_days = (
        db.session.query(Workout.workout_date)
        .filter(Workout.user_id == current_user.id)
        .filter(Workout.workout_date >= streak_window_start, Workout.workout_date <= today)
        .distinct()
        .all()
    )
    meal_days = (
        db.session.query(MealEntry.entry_date)
        .filter(MealEntry.user_id == current_user.id)
        .filter(MealEntry.entry_date >= streak_window_start, MealEntry.entry_date <= today)
        .distinct()
        .all()
    )
    weight_days = (
        db.session.query(WeightEntry.entry_date)
        .filter(WeightEntry.user_id == current_user.id)
        .filter(WeightEntry.entry_date >= streak_window_start, WeightEntry.entry_date <= today)
        .distinct()
        .all()
    )

    logged_days = set([r[0] for r in workout_days]) | set([r[0] for r in meal_days]) | set([r[0] for r in weight_days])

    streak = 0
    d = today
    while d >= streak_window_start:
        if d in logged_days:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    # ----------------------------
    # ACTIVITY CHART TOGGLE (4w vs 6m) - existing
    # ----------------------------
    chart_range = (request.args.get("range") or "4w").strip().lower()
    if chart_range not in ("4w", "6m"):
        chart_range = "4w"

    activity_labels = []
    activity_counts = []
    activity_minutes = []

    if chart_range == "4w":
        four_weeks_start = start_of_week - timedelta(weeks=3)

        for i in range(4):
            wk_start = four_weeks_start + timedelta(weeks=i)
            wk_end = wk_start + timedelta(days=6)

            activity_labels.append(wk_start.strftime("%d %b"))

            wk_count = (
                Workout.query.filter(
                    Workout.user_id == current_user.id,
                    Workout.workout_date >= wk_start,
                    Workout.workout_date <= wk_end,
                ).count()
            )
            activity_counts.append(wk_count)

            wk_minutes = (
                db.session.query(db.func.coalesce(db.func.sum(Workout.duration_minutes), 0))
                .filter(
                    Workout.user_id == current_user.id,
                    Workout.workout_date >= wk_start,
                    Workout.workout_date <= wk_end,
                )
                .scalar()
            )
            activity_minutes.append(int(wk_minutes or 0))
    else:
        y = today.year
        m = today.month

        month_starts = []
        for _ in range(6):
            month_starts.append(date(y, m, 1))
            m -= 1
            if m == 0:
                m = 12
                y -= 1

        month_starts.reverse()

        for ms in month_starts:
            last_day = calendar.monthrange(ms.year, ms.month)[1]
            me = date(ms.year, ms.month, last_day)

            activity_labels.append(ms.strftime("%b %Y"))

            m_count = (
                Workout.query.filter(
                    Workout.user_id == current_user.id,
                    Workout.workout_date >= ms,
                    Workout.workout_date <= me,
                ).count()
            )
            activity_counts.append(m_count)

            m_minutes = (
                db.session.query(db.func.coalesce(db.func.sum(Workout.duration_minutes), 0))
                .filter(
                    Workout.user_id == current_user.id,
                    Workout.workout_date >= ms,
                    Workout.workout_date <= me,
                )
                .scalar()
            )
            activity_minutes.append(int(m_minutes or 0))

    # ----------------------------
    # PERSONAL RECORDS (existing)
    # ----------------------------
    pr_rows = (
        db.session.query(
            WorkoutExercise.name.label("exercise_name"),
            db.func.max(WorkoutSet.weight).label("max_weight"),
        )
        .join(WorkoutSet, WorkoutSet.exercise_id == WorkoutExercise.id)
        .join(Workout, Workout.id == WorkoutExercise.workout_id)
        .filter(Workout.user_id == current_user.id)
        .filter(WorkoutSet.weight.isnot(None))
        .group_by(WorkoutExercise.name)
        .all()
    )

    personal_records = []
    for row in pr_rows:
        ex_name = row.exercise_name
        max_w = float(row.max_weight or 0)

        latest_date = (
            db.session.query(db.func.max(Workout.workout_date))
            .join(WorkoutExercise, WorkoutExercise.workout_id == Workout.id)
            .join(WorkoutSet, WorkoutSet.exercise_id == WorkoutExercise.id)
            .filter(Workout.user_id == current_user.id)
            .filter(WorkoutExercise.name == ex_name)
            .filter(WorkoutSet.weight == max_w)
            .scalar()
        )

        personal_records.append({"name": ex_name, "weight": max_w, "date": latest_date})

    personal_records.sort(key=lambda x: (-x["weight"], x["name"].lower()))
    personal_records_top = personal_records[:5]

    # ----------------------------
    # EXERCISE PROGRESSION (existing)
    # ----------------------------
    exercise_names = (
        db.session.query(WorkoutExercise.name)
        .join(Workout, Workout.id == WorkoutExercise.workout_id)
        .filter(Workout.user_id == current_user.id)
        .distinct()
        .order_by(WorkoutExercise.name.asc())
        .all()
    )
    exercise_names = [r[0] for r in exercise_names]

    selected_exercise = (request.args.get("exercise") or "").strip()
    if not selected_exercise and exercise_names:
        selected_exercise = exercise_names[0]
    if selected_exercise and selected_exercise not in exercise_names and exercise_names:
        selected_exercise = exercise_names[0]

    prog_labels = []
    prog_weights = []

    if selected_exercise:
        rows = (
            db.session.query(
                Workout.workout_date.label("d"),
                db.func.max(WorkoutSet.weight).label("max_w"),
            )
            .join(WorkoutExercise, WorkoutExercise.workout_id == Workout.id)
            .join(WorkoutSet, WorkoutSet.exercise_id == WorkoutExercise.id)
            .filter(Workout.user_id == current_user.id)
            .filter(WorkoutExercise.name == selected_exercise)
            .filter(WorkoutSet.weight.isnot(None))
            .group_by(Workout.workout_date)
            .order_by(Workout.workout_date.asc())
            .all()
        )

        prog_labels = [r.d.strftime("%d %b %Y") for r in rows]
        prog_weights = [float(r.max_w or 0) for r in rows]

    return render_template(
        "dashboard/dashboard.html",
        # date info
        start_of_week=start_of_week,
        today=today,
        # workout summary
        total_workouts=total_workouts,
        workouts_this_week=workouts_this_week,
        minutes_this_week=minutes_this_week,
        total_minutes_all_time=total_minutes_all_time,
        latest_workouts=latest_workouts,
        weekly_goal=weekly_goal,
        goal_percent=goal_percent,
        # dashboard integration
        streak=streak,
        avg_calories_7d=avg_calories_7d,
        cal_labels_7d=cal_labels_7d,
        cal_values_7d=cal_values_7d,
        latest_weight_kg=latest_weight_kg,
        latest_weight_date=latest_weight_date,
        weight_labels_30d=weight_labels_30d,
        weight_values_30d=weight_values_30d,
        # activity chart
        chart_labels=activity_labels,
        chart_counts=activity_counts,
        chart_minutes=activity_minutes,
        chart_range=chart_range,
        # PRs + progression
        personal_records=personal_records_top,
        exercise_names=exercise_names,
        selected_exercise=selected_exercise,
        prog_labels=prog_labels,
        prog_weights=prog_weights,
    )