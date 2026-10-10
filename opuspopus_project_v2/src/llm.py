"""LLM wrapper: Gemini (cloud) or Ollama (local), JSON output, disk cache, retries."""
import hashlib, json, re, time
import requests
from src import config

_last_call = 0.0
_gemini = None


class LLMError(Exception):
    pass


def provider_name():
    if config.LLM_PROVIDER == "ollama":
        return f"Ollama ({config.OLLAMA_MODEL})"
    return f"Gemini ({config.GEMINI_MODEL})"


def _parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()  # deepseek-r1
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise LLMError(f"LLM did not return JSON: {text[:200]}")


def _call_gemini(prompt):
    global _gemini
    if not config.GEMINI_API_KEY or "paste" in config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY missing in .env")
    if _gemini is None:
        from google import genai
        _gemini = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = _gemini.models.generate_content(
        model=config.GEMINI_MODEL, contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0})
    return resp.text


def _call_ollama(prompt):
    r = requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=300, json={
        "model": config.OLLAMA_MODEL, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["message"]["content"]


def ask_json(prompt, retries=4):
    """Send prompt, return parsed JSON. Identical prompts are served from disk cache."""
    global _last_call
    key = hashlib.sha256(f"{provider_name()}|{prompt}".encode()).hexdigest()[:24]
    cache_file = config.CACHE / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    call = _call_ollama if config.LLM_PROVIDER == "ollama" else _call_gemini
    last_err = None
    for attempt in range(retries):
        wait = config.LLM_MIN_INTERVAL - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            _last_call = time.time()
            data = _parse_json(call(prompt))
            cache_file.write_text(json.dumps(data, indent=1), encoding="utf-8")
            return data
        except LLMError as e:
            last_err = e
            if "missing" in str(e):
                raise
        except Exception as e:  # rate limit / network
            last_err = e
            rate = "429" in str(e) or "RESOURCE" in str(e)
            time.sleep(min(30, 8 * (attempt + 1)) if rate else 2)
    raise LLMError(f"LLM failed after {retries} tries: {last_err}")
