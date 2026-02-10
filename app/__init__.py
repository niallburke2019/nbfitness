from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

login_manager.login_view = "auth.login"  # change if your login endpoint differs


def create_app():
    app = Flask(__name__)

    # --- config ---
    app.config["SECRET_KEY"] = app.config.get("SECRET_KEY") or "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        app.config.get("SQLALCHEMY_DATABASE_URI") or "sqlite:///nb_fitness.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- init extensions ---
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)  # ✅ enables `flask db ...`

    # --- user loader ---
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # --- register blueprints ---
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dash_bp
    from app.routes.workouts import workouts_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(workouts_bp)

    return app
