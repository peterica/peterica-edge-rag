"""환경 변수 기반 설정"""

import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
SERVER_EMBED_MODEL = os.getenv("SERVER_EMBED_MODEL", "bge-m3")
MOBILE_EMBED_MODEL = os.getenv("MOBILE_EMBED_MODEL", "dragonkue/multilingual-e5-small-ko-v2")
MOBILE_EMBED_BACKEND = os.getenv("MOBILE_EMBED_BACKEND", "sentence-transformers")  # ollama | sentence-transformers

WIKI_DIR = os.getenv(
    "WIKI_DIR",
    "/Users/seodong-eok/peterica/semi-project/peterica-blog-wiki/wiki",
)
SERVER_DB_PATH = os.getenv("SERVER_DB_PATH", "./data/server.db")
MOBILE_DB_PATH = os.getenv("MOBILE_DB_PATH", "./data/mobile.db")

SERVER_EMBED_DIM = int(os.getenv("SERVER_EMBED_DIM", "1024"))
MOBILE_EMBED_DIM = int(os.getenv("MOBILE_EMBED_DIM", "384"))

TOP_K = int(os.getenv("TOP_K", "12"))
RAG_DISTANCE_MAX = float(os.getenv("RAG_DISTANCE_MAX", "0.65"))
RAG_MIN_K = int(os.getenv("RAG_MIN_K", "3"))
RAG_MAX_K = int(os.getenv("RAG_MAX_K", "3"))

SERVER_LLM_MODEL = os.getenv("SERVER_LLM_MODEL", "gemma4:e4b-it-q4_K_M")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60.0"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8600"))

SERVER_API_KEY = os.getenv("SERVER_API_KEY", "")  # 빈 값이면 인증 비활성
