import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["DATA_PATH"] = Path(app.root_path).parent / "data" / "NutriAI_Final_Dataset_Food_Catalog.csv"
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024

    from .routes import bp
    app.register_blueprint(bp)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if request.path.startswith("/api/"):
            if isinstance(error, HTTPException):
                return jsonify(error=error.description), error.code
            app.logger.exception("Unhandled API error")
            return jsonify(error="Unexpected server error. Check the Flask terminal for details."), 500
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Unhandled page error")
        return "Internal server error", 500

    return app
