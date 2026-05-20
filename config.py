"""
Central configuration for the Flask/Docker/AWS course assistant.

Values can be overridden via environment variables or a local .env file.
The defaults match the original course rag_example.py so the app works
out of the box without any setup.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
INDEX_CACHE_DIR = BASE_DIR / "index_cache"
DB_PATH = BASE_DIR / "chat.db"
GENERATED_DIR = DATA_DIR / "generated"
GENERATED_IMAGES_DIR = GENERATED_DIR / "images"
SAMPLE_UPLOADS_DIR = BASE_DIR / "sample_uploads"

# Starter knowledge-base files preserved by Clear All / Reset Project.
STARTER_KB_FILES = frozenset({
    "Avidan Risk Analysis Report.txt",
    "docker_aws.pdf",
    "Flask-lecture1.pdf",
    "Flask-lecture2.pdf",
    "for_check.txt",
})

# Strict RAG refusal messages (no general-knowledge fallback).
REFUSAL_TEXT_EN = (
    "I do not have enough information in the provided documents to answer this question."
)
REFUSAL_TEXT_HE = (
    "אין לי מספיק מידע במסמכים הקיימים כדי לענות על השאלה הזאת."
)

# When the knowledge base is empty or not indexed yet.
NO_KB_TEXT_EN = (
    "I do not have a knowledge base available to answer this question."
)
NO_KB_TEXT_HE = (
    "אין לי בסיס נתונים זמין כדי לענות על השאלה הזאת."
)


# --- API credentials ------------------------------------------------------
# Must be supplied via environment variables or a local .env file.
# No real keys are kept in source so the Docker image stays free of secrets.

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")


# --- Models ---------------------------------------------------------------
HF_EMBEDDING_MODEL = os.getenv(
    "HF_EMBEDDING_MODEL",
    "ibm-granite/granite-embedding-97m-multilingual-r2",
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


# --- Retrieval / chunking -------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))
TOP_K = int(os.getenv("TOP_K", "6"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "8"))

# Minimum cosine similarity for a chunk to be considered "relevant".
# Below this the assistant should refuse to answer.
MIN_SCORE_THRESHOLD = float(os.getenv("MIN_SCORE_THRESHOLD", "0.30"))


# --- Flask ----------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
