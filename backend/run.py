"""Flask entry point for Pulse backend."""
import os
import sys

# Ensure the backend/ directory is on sys.path so 'app' is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("run")

app = create_app(Config)

if __name__ == "__main__":
    port = Config.PORT
    debug = Config.DEBUG
    logger.info(f"Starting Pulse backend on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
