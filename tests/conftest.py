import os
import pytest

from app import create_app, db
from app.models import User


@pytest.fixture()
def app(tmp_path):
    # Use file-based sqlite for Windows reliability
    db_file = tmp_path / "test.db"
    test_db_uri = f"sqlite:///{db_file}"

    # Set env vars BEFORE create_app()
    os.environ["DATABASE_URL"] = test_db_uri
    os.environ["API_KEY"] = "supersecret123"

    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        LOGIN_DISABLED=False,
    )

    with app.app_context():
        db.create_all()

        u = User(email="test@example.com")
        if hasattr(u, "set_password"):
            u.set_password("Password123!")
        else:
            setattr(u, "password_hash", "test")

        db.session.add(u)
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()

    try:
        db.engine.dispose()
    except Exception:
        pass

    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("API_KEY", None)


@pytest.fixture()
def client(app):
    with app.test_client() as client:
        # ✅ Guaranteed header for Flask/Werkzeug: becomes request.headers["X-API-KEY"]
        client.environ_base["HTTP_X_API_KEY"] = os.environ.get("API_KEY", "")
        yield client