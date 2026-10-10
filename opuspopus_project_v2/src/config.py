import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
CACHE = DATA / "cache"
for d in (DATA, OUTPUTS, CACHE):
    d.mkdir(exist_ok=True)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
EMBED_MODEL = os.getenv("EMBED_MODEL", "thenlper/gte-small")
LLM_MIN_INTERVAL = float(os.getenv("LLM_MIN_INTERVAL", "1"))
MAX_RULES = 12  # max inclusion + max exclusion criteria judged per trial
