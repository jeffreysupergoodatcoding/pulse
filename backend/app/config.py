import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    PORT = int(os.getenv("BACKEND_PORT", 5001))

    # LLM
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
    LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

    # Zep Cloud
    ZEP_API_KEY = os.getenv("ZEP_API_KEY", "")

    # Reddit
    REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "pulse/1.0")

    # Twitter / X
    TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
    TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")

    # YouTube
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    # Redis (optional)
    REDIS_URL = os.getenv("REDIS_URL", "")

    # Simulation defaults
    DEFAULT_SIM_ROUNDS = int(os.getenv("DEFAULT_SIM_ROUNDS", 50))
    DEFAULT_N_AGENTS = int(os.getenv("DEFAULT_N_AGENTS", 100))
    DEFAULT_N_ARCHETYPES = int(os.getenv("DEFAULT_N_ARCHETYPES", 8))
    SENTIMENT_SCORER_MODE = os.getenv("SENTIMENT_SCORER_MODE", "llm")

    # Data directories
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    ENTITIES_DIR = os.path.join(DATA_DIR, "entities")
    SIMULATIONS_DIR = os.path.join(DATA_DIR, "simulations")
