from __future__ import annotations

from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


def utcnow() -> datetime:
    """UTC timestamp (naive). Best compatibility with SQL Server datetime2."""
    return datetime.utcnow()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # Use datetime2 in SQL Server (naive UTC in Python)
    created_at = db.Column(db.DateTime(), nullable=False, default=utcnow)

    workouts = db.relationship(
        "Workout",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    meal_entries = db.relationship(
        "MealEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # one-to-one macro goal
    macro_goal = db.relationship(
        "MacroGoal",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # bodyweight logs
    weight_entries = db.relationship(
        "WeightEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # flask-login compatibility
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Workout(db.Model):
    __tablename__ = "workouts"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(120), nullable=False)
    workout_date = db.Column(db.Date, nullable=False, index=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=0)

    notes = db.Column(db.Text, nullable=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    created_at = db.Column(db.DateTime(), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    user = db.relationship("User", back_populates="workouts")

    exercises = db.relationship(
        "WorkoutExercise",
        back_populates="workout",
        cascade="all, delete-orphan",
        order_by="WorkoutExercise.position.asc()",
    )

    def total_sets(self) -> int:
        return sum(ex.total_sets() for ex in self.exercises)

    def total_reps(self) -> int:
        return sum(ex.total_reps() for ex in self.exercises)

    def total_volume(self) -> float:
        return sum(ex.total_volume() for ex in self.exercises)

    def safe_duration(self) -> int:
        return int(self.duration_minutes or 0)


class WorkoutExercise(db.Model):
    __tablename__ = "workout_exercises"

    id = db.Column(db.Integer, primary_key=True)

    workout_id = db.Column(
        db.Integer,
        db.ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(120), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)

    workout = db.relationship("Workout", back_populates="exercises")

    sets = db.relationship(
        "WorkoutSet",
        back_populates="exercise",
        cascade="all, delete-orphan",
        order_by="WorkoutSet.position.asc()",
    )

    def total_sets(self) -> int:
        return len(self.sets)

    def total_reps(self) -> int:
        return sum(int(s.reps or 0) for s in self.sets)

    def total_volume(self) -> float:
        total = 0.0
        for s in self.sets:
            w = float(s.weight or 0)
            r = int(s.reps or 0)
            total += (w * r)
        return total


class WorkoutSet(db.Model):
    __tablename__ = "workout_sets"

    id = db.Column(db.Integer, primary_key=True)

    exercise_id = db.Column(
        db.Integer,
        db.ForeignKey("workout_exercises.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    weight = db.Column(db.Float, nullable=True)
    reps = db.Column(db.Integer, nullable=True)

    position = db.Column(db.Integer, nullable=False, default=0)

    exercise = db.relationship("WorkoutExercise", back_populates="sets")


class MealEntry(db.Model):
    __tablename__ = "meal_entries"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    entry_date = db.Column(db.Date, nullable=False, index=True)

    meal_type = db.Column(db.String(20), nullable=False, default="lunch", index=True)

    food_name = db.Column(db.String(255), nullable=False)

    calories = db.Column(db.Integer, nullable=False, default=0)
    protein_g = db.Column(db.Float, nullable=False, default=0.0)
    carbs_g = db.Column(db.Float, nullable=False, default=0.0)
    fat_g = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime(), nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="meal_entries")


class MacroGoal(db.Model):
    __tablename__ = "macro_goals"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    calories_target = db.Column(db.Integer, nullable=False, default=0)
    protein_target_g = db.Column(db.Float, nullable=False, default=0.0)
    carbs_target_g = db.Column(db.Float, nullable=False, default=0.0)
    fat_target_g = db.Column(db.Float, nullable=False, default=0.0)

    updated_at = db.Column(
        db.DateTime(),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    user = db.relationship("User", back_populates="macro_goal")


class WeightEntry(db.Model):
    __tablename__ = "weight_entries"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    entry_date = db.Column(db.Date, nullable=False, index=True)

    weight_kg = db.Column(db.Float, nullable=False)

    created_at = db.Column(db.DateTime(), nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="weight_entries")

    __table_args__ = (
        db.UniqueConstraint("user_id", "entry_date", name="uq_weight_user_date"),
    )