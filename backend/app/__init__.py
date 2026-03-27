from flask import Flask
from flask_cors import CORS

from app.config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from app.routes.ingestion_routes import ingestion_bp
    from app.routes.graph_routes import graph_bp
    from app.routes.simulation_routes import simulation_bp
    from app.routes.report_routes import report_bp
    from app.routes.persona_routes import persona_bp

    app.register_blueprint(ingestion_bp, url_prefix="/api/ingestion")
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    app.register_blueprint(report_bp, url_prefix="/api/report")
    app.register_blueprint(persona_bp, url_prefix="/api/persona")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "pulse"}

    return app
