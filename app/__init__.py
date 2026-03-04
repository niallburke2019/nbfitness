# app/__init__.py
from __future__ import annotations

import os

from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv

from flasgger import Swagger
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix


# ------------------------------------------------------------
# Extensions
# ------------------------------------------------------------
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


# ------------------------------------------------------------
# Rate limiter (global)
# ------------------------------------------------------------
def rate_limit_key() -> str:
    """
    Prefer API key (so Postman / API clients get consistent limits),
    then logged-in user id, else fallback to IP.
    """
    api_key = (request.headers.get("X-API-KEY") or "").strip()
    if api_key:
        return f"api_key:{api_key}"

    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            return f"user:{current_user.get_id()}"
    except Exception:
        pass

    return get_remote_address()


# ✅ Explicit storage_uri removes the “in-memory storage not specified” warning
# You can set RATELIMIT_STORAGE_URI=redis://... later for production.
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[
        "500 per day",
        "120 per hour",
    ],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)


def create_app() -> Flask:
    load_dotenv(override=False)

    app = Flask(__name__, instance_relative_config=True)

    # -----------------------
    # Basic Configuration
    # -----------------------
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")

    # Environment flag (simple + reliable)
    # Set FLASK_ENV=production (or APP_ENV=production) when deployed
    env = (os.getenv("FLASK_ENV") or os.getenv("APP_ENV") or "development").lower()
    is_production = env == "production"

    # ✅ Dev quality-of-life (doesn't affect prod)
    app.config["TEMPLATES_AUTO_RELOAD"] = not is_production
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    # ✅ Cookie / session hardening
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production,  # don't break local dev
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=is_production,
    )

    # ✅ Behind-proxy support (Azure / reverse proxy)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Ensure instance folder exists (important on Windows)
    os.makedirs(app.instance_path, exist_ok=True)

    # -----------------------
    # Database (PINNED to instance/nb_fitness.db)
    # -----------------------
    default_db_path = os.path.join(app.instance_path, "nb_fitness.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{default_db_path}",
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # -----------------------
    # Rate limiting enable/disable
    # -----------------------
    # Off automatically for pytest
    if "PYTEST_CURRENT_TEST" in os.environ:
        app.config["RATELIMIT_ENABLED"] = False

    # Also allow explicit env override:
    # RATELIMIT_ENABLED=false
    ratelimit_enabled_env = (os.getenv("RATELIMIT_ENABLED") or "").strip().lower()
    if ratelimit_enabled_env in {"0", "false", "no"}:
        app.config["RATELIMIT_ENABLED"] = False

    # -----------------------
    # Initialise Extensions
    # -----------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    # -----------------------
    # Swagger / OpenAPI Docs
    # -----------------------
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec_1",
                "route": "/apidocs/apispec_1.json",
                "rule_filter": lambda rule: True,  # include all
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }

    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "NB Fitness API",
            "description": "REST API for Meals (CRUD) with API key authentication and rate limiting.",
            "version": "1.0.0",
        },
        "basePath": "/",
        "schemes": ["https", "http"],
    }

    Swagger(app, config=swagger_config, template=swagger_template)

    # -----------------------
    # User Loader
    # -----------------------
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        # ✅ SQLAlchemy 2.x style (fixes LegacyAPIWarning)
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # -----------------------
    # Register Blueprints
    # -----------------------
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dash_bp
    from app.routes.workouts import workouts_bp
    from app.routes.meals import meals_bp
    from app.routes.weight import weight_bp
    from app.routes.api import api_bp
    from app.routes.account import account_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(workouts_bp)
    app.register_blueprint(meals_bp)
    app.register_blueprint(weight_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(account_bp)

    # -----------------------
    # Error Handlers
    # -----------------------
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    return app