"""
Central configuration for ScoutMatch AI.

Values can be overridden via environment variables or a local .env file.
Local FAISS mode remains available for development; AWS Knowledge Base is
the production path when RAG_BACKEND=aws_kb.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env", override=True)
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
INDEX_CACHE_DIR = BASE_DIR / "index_cache"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "chat.db"))).expanduser()
GENERATED_DIR = DATA_DIR / "generated"
GENERATED_IMAGES_DIR = GENERATED_DIR / "images"
SAMPLE_UPLOADS_DIR = BASE_DIR / "sample_uploads"
SAMPLE_SCOUT_DATA_DIR = BASE_DIR / "sample_scout_data"

# Starter knowledge-base files preserved by Clear All / Reset Project (local mode).
STARTER_KB_FILES = frozenset({
    "Avidan Risk Analysis Report.txt",
    "docker_aws.pdf",
    "Flask-lecture1.pdf",
    "Flask-lecture2.pdf",
    "for_check.txt",
})

# Strict RAG refusal messages — ScoutMatch player/team documents only.
REFUSAL_TEXT_EN = (
    "I do not have enough information in the uploaded player and team documents "
    "to answer this question."
)
REFUSAL_TEXT_HE = (
    "אין לי מספיק מידע במסמכי השחקנים ובמסמכי הקבוצה כדי לענות על השאלה הזאת."
)

NO_KB_TEXT_EN = (
    "Upload player CVs or scouting reports to start recruiting. "
    "I cannot answer until documents are indexed in the knowledge base."
)
NO_KB_TEXT_HE = (
    "העלה קורות חיים של שחקנים או דוחות סקאuting כדי להתחיל. "
    "לא ניתן לענות עד שהמסמכים מאונדקסים בבסיס הידע."
)

SCOUTMATCH_SYSTEM_PROMPT = """You are ScoutMatch AI, an AI-powered football recruitment assistant.

Answer only from retrieved player CVs, scouting reports, interview notes, and team requirement documents.
Do not use general knowledge.
Do not invent player names, salaries, experience, relocation preferences, skills, clubs, or achievements.

Always answer in the same language as the user's question.

When recommending a player:
- State the player's full name explicitly.
- List the exact supporting facts from the documents.
- Check every mandatory requirement carefully before claiming a match.
- Preserve all numeric values exactly as written in the documents.
- Never claim that a numeric requirement is satisfied when it is not
  (for example, 4 years of experience does NOT satisfy a minimum of 5 years).
- Never claim salary, relocation, or skill requirements are met unless the documents support it.
- If no player satisfies all mandatory requirements, say clearly that no exact match was found.
  In Hebrew you may say: "לא נמצא מועמד שעומד בכל דרישות החובה."
- You may identify the strongest partial match, but clearly label it as a partial match
  and explain which mandatory requirements are not satisfied.
- Clearly state that the result is an AI-assisted assessment based on uploaded documents only.
- Do not claim certainty when the documents are incomplete.

Never expose internal passage markers, retrieval IDs, or placeholders such as Passage %[4]% or %[4]%.
Do not reference internal retrieval numbering.
Cite evidence using readable document facts and player names, not passage labels.

If the uploaded documents do not provide enough evidence, return the strict refusal message only."""


# --- RAG backend selection ------------------------------------------------
RAG_BACKEND = os.getenv("RAG_BACKEND", "local").strip().lower()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_KB_ID = os.getenv("BEDROCK_KB_ID", "")
BEDROCK_DATA_SOURCE_ID = os.getenv("BEDROCK_DATA_SOURCE_ID", "")
BEDROCK_MODEL_ARN = os.getenv(
    "BEDROCK_MODEL_ARN",
    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
)
AWS_KB_TOP_K = int(os.getenv("AWS_KB_TOP_K", "5"))
AWS_KB_RETRIEVE_CANDIDATES = int(os.getenv("AWS_KB_RETRIEVE_CANDIDATES", "30"))
AWS_KB_CONTEXT_SOURCE_LIMIT = int(os.getenv("AWS_KB_CONTEXT_SOURCE_LIMIT", "10"))
AWS_KB_MAX_CHUNKS_PER_SOURCE = int(os.getenv("AWS_KB_MAX_CHUNKS_PER_SOURCE", "2"))
AWS_KB_CONTEXT_EXCERPT_MAX = int(os.getenv("AWS_KB_CONTEXT_EXCERPT_MAX", "1200"))
AWS_KB_MIN_SCORE = os.getenv("AWS_KB_MIN_SCORE", "")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "")
AWS_S3_PREFIX = os.getenv("AWS_S3_PREFIX", "scoutmatch/knowledge-base/")
SCOUTMATCH_ADMIN_TOKEN = os.getenv("SCOUTMATCH_ADMIN_TOKEN", "")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


# --- API credentials (local mode) -----------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")


# --- Models (local mode) --------------------------------------------------
HF_EMBEDDING_MODEL = os.getenv(
    "HF_EMBEDDING_MODEL",
    "ibm-granite/granite-embedding-97m-multilingual-r2",
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


# --- Retrieval / chunking (local mode) ------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))
TOP_K = int(os.getenv("TOP_K", "6"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "8"))
MIN_SCORE_THRESHOLD = float(os.getenv("MIN_SCORE_THRESHOLD", "0.30"))


# --- Flask ----------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"


# --- Bedrock ingestion contention -----------------------------------------
INGESTION_TOTAL_TIMEOUT_SECONDS = int(os.getenv("INGESTION_TOTAL_TIMEOUT_SECONDS", "180"))
INGESTION_POLL_INTERVAL_SECONDS = float(os.getenv("INGESTION_POLL_INTERVAL_SECONDS", "3"))
INGESTION_RETRY_DELAY_SECONDS = float(os.getenv("INGESTION_RETRY_DELAY_SECONDS", "2"))
INGESTION_MAX_START_ATTEMPTS = int(os.getenv("INGESTION_MAX_START_ATTEMPTS", "20"))
INGESTION_TIMEOUT_USER_MESSAGE = (
    "The knowledge base is still updating. Please try again shortly."
)


# --- Upload allowlist (ScoutMatch documents) ------------------------------
DOC_UPLOAD_EXTENSIONS = frozenset({
    ".txt", ".md", ".html", ".pdf", ".doc", ".docx", ".csv", ".xls", ".xlsx",
})
IMAGE_UPLOAD_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
ENABLE_IMAGE_UPLOADS = os.getenv("ENABLE_IMAGE_UPLOADS", "false").lower() == "true"


def parse_min_score(value: str | None) -> float | None:
    """Return float threshold or None when unset (no score filter)."""
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


AWS_KB_MIN_SCORE_FLOAT = parse_min_score(AWS_KB_MIN_SCORE)


def validate_aws_config() -> list[str]:
    """Return list of missing required AWS settings (empty when valid)."""
    if RAG_BACKEND != "aws_kb":
        return []
    missing: list[str] = []
    if not (BEDROCK_KB_ID or "").strip():
        missing.append("BEDROCK_KB_ID")
    if not (BEDROCK_DATA_SOURCE_ID or "").strip():
        missing.append("BEDROCK_DATA_SOURCE_ID")
    if not (BEDROCK_MODEL_ARN or "").strip():
        missing.append("BEDROCK_MODEL_ARN")
    if not (AWS_S3_BUCKET or "").strip():
        missing.append("AWS_S3_BUCKET")
    if not (AWS_S3_PREFIX or "").strip():
        missing.append("AWS_S3_PREFIX")
    return missing


def normalised_s3_prefix() -> str:
    """Ensure prefix ends with / for S3 list/upload operations."""
    prefix = (AWS_S3_PREFIX or "").strip()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return prefix
