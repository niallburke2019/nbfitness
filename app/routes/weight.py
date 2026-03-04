from __future__ import annotations

from datetime import datetime, date, timedelta
from io import StringIO
import csv

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import login_required, current_user

from app import db
from app.models import WeightEntry

weight_bp = Blueprint("weight", __name__, url_prefix="/weight")


def _parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _get_entry_or_404(entry_id: int) -> WeightEntry:
    e = WeightEntry.query.get_or_404(entry_id)
    if e.user_id != current_user.id:
        abort(403)
    return e


@weight_bp.get("/")
@login_required
def index():
    # Show latest entries + 30-day chart
    entries = (
        WeightEntry.query.filter_by(user_id=current_user.id)
        .order_by(WeightEntry.entry_date.desc())
        .limit(30)
        .all()
    )

    latest = entries[0] if entries else None

    end = date.today()
    start = end - timedelta(days=29)

    rows = (
        db.session.query(
            WeightEntry.entry_date.label("d"),
            WeightEntry.weight_kg.label("w"),
        )
        .filter(WeightEntry.user_id == current_user.id)
        .filter(WeightEntry.entry_date >= start, WeightEntry.entry_date <= end)
        .order_by(WeightEntry.entry_date.asc())
        .all()
    )

    by_day = {r.d: float(r.w) for r in rows}

    labels = []
    weights = []
    d = start
    while d <= end:
        labels.append(d.strftime("%d %b"))
        weights.append(by_day.get(d, None))  # allow gaps
        d += timedelta(days=1)

    return render_template(
        "weight/index.html",
        entries=entries,
        latest=latest,
        labels=labels,
        weights=weights,
        start=start,
        end=end,
    )


@weight_bp.get("/new")
@login_required
def create_get():
    selected = _parse_date(request.args.get("date")) or date.today()
    return render_template("weight/create.html", selected_date=selected)


@weight_bp.post("/new")
@login_required
def create_post():
    entry_date = _parse_date(request.form.get("entry_date")) or date.today()
    weight_raw = (request.form.get("weight_kg") or "").strip()

    try:
        w = float(weight_raw)
        if w <= 0:
            raise ValueError
    except ValueError:
        flash("Enter a valid weight in kg.", "danger")
        return redirect(url_for("weight.create_get", date=entry_date.strftime("%Y-%m-%d")))

    # Upsert (one per day)
    existing = WeightEntry.query.filter_by(user_id=current_user.id, entry_date=entry_date).first()
    if existing:
        existing.weight_kg = w
        db.session.commit()
        flash("Weight updated for that date.", "success")
        return redirect(url_for("weight.index"))

    entry = WeightEntry(user_id=current_user.id, entry_date=entry_date, weight_kg=w)
    db.session.add(entry)
    db.session.commit()
    flash("Weight logged.", "success")
    return redirect(url_for("weight.index"))


@weight_bp.get("/<int:entry_id>/edit")
@login_required
def edit_get(entry_id: int):
    entry = _get_entry_or_404(entry_id)
    return render_template("weight/edit.html", entry=entry)


@weight_bp.post("/<int:entry_id>/edit")
@login_required
def edit_post(entry_id: int):
    entry = _get_entry_or_404(entry_id)
    weight_raw = (request.form.get("weight_kg") or "").strip()

    try:
        w = float(weight_raw)
        if w <= 0:
            raise ValueError
    except ValueError:
        flash("Enter a valid weight in kg.", "danger")
        return redirect(url_for("weight.edit_get", entry_id=entry_id))

    entry.weight_kg = w
    db.session.commit()
    flash("Weight entry updated.", "success")
    return redirect(url_for("weight.index"))


@weight_bp.post("/<int:entry_id>/delete")
@login_required
def delete_post(entry_id: int):
    entry = _get_entry_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    flash("Weight entry deleted.", "warning")
    return redirect(url_for("weight.index"))


# -----------------------
# CSV EXPORT (Step 5)
# -----------------------
@weight_bp.get("/export.csv")
@login_required
def export_csv():
    entries = (
        WeightEntry.query.filter_by(user_id=current_user.id)
        .order_by(WeightEntry.entry_date.asc())
        .all()
    )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "weight_kg"])

    for e in entries:
        writer.writerow([e.entry_date.strftime("%Y-%m-%d"), f"{float(e.weight_kg):.1f}"])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=bodyweight_export.csv"},
    )