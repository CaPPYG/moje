"""
BrainDump — LLM integration (Groq primary, Gemini fallback)
Extracts structured tasks from raw voice transcript text,
including due_date detection from natural language date expressions.
"""
import os
import json
import logging
import httpx
from datetime import date, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
GEMINI_MODEL = "gemini-1.5-flash"

# Slovak day names for context
_SK_DAYS = ["pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"]


def _today_context() -> str:
    """Build a date context string for the LLM (today's date + day name)."""
    today = date.today()
    day_name = _SK_DAYS[today.weekday()]
    return f"Dnes je {day_name} {today.strftime('%d.%m.%Y')} (ISO: {today.isoformat()})."


SYSTEM_PROMPT_TEMPLATE = """\
You are a task extraction assistant. Analyze the voice transcript and extract ALL actionable tasks/to-dos.
Return ONLY a valid JSON object with no additional text, markdown, or explanation.

{date_context}

Categories MUST be one of: Work, Groceries, Personal, Other

Rules:
- Extract every distinct action item mentioned
- If someone says "kup mlieko a vajcia", create TWO separate tasks
- Keep task text concise but complete
- CRITICAL: Always keep the task text in the SAME language as the spoken transcript (e.g. Slovak stays Slovak, English stays English). Do NOT translate.
- If no tasks found, return {{"tasks": []}}

Due date detection (due_date field):
- Detect ALL relative and absolute date expressions in Slovak, Czech, and English
- Examples: "zajtra" → tomorrow, "pozajtra" → day after tomorrow, "tento piatok" → next/this Friday,
  "budúci pondelok" → next Monday, "o týždeň" → in one week, "15. októbra" → Oct 15 of current year,
  "dnes" → today, "cez víkend" → nearest Saturday
- Translate detected date to ISO format: "YYYY-MM-DD"
- If NO date is mentioned or unclear, set due_date to null
- Use today's date ({today_iso}) as the reference point for relative dates

Required JSON format:
{{"tasks": [{{"text": "task description", "category": "Work|Groceries|Personal|Other", "due_date": "YYYY-MM-DD or null"}}]}}\
"""


def _build_system_prompt() -> str:
    today = date.today()
    return SYSTEM_PROMPT_TEMPLATE.format(
        date_context=_today_context(),
        today_iso=today.isoformat(),
    )


def _build_user_message(raw_text: str) -> str:
    return f'Extract tasks from this voice transcript:\n\n"{raw_text}"'


async def _call_groq(raw_text: str, timeout: float = 15.0) -> Optional[list[dict]]:
    """Call Groq API trying primary model, then fallback model."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return None

    system_prompt = _build_system_prompt()

    for model in GROQ_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _build_user_message(raw_text)},
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {groq_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return parsed.get("tasks", [])
        except Exception as e:
            logger.warning(f"Groq API error with model {model}: {e}")
            continue

    return None


async def _call_gemini(raw_text: str, timeout: float = 20.0) -> Optional[list[dict]]:
    """Call Gemini 1.5 Flash as fallback."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        return None

    system_prompt = _build_system_prompt()

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{system_prompt}\n\n{_build_user_message(raw_text)}"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={gemini_key}",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            # Gemini sometimes wraps in ```json
            content = content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            parsed = json.loads(content)
            return parsed.get("tasks", [])
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return None


def _validate_due_date(raw: Optional[str]) -> Optional[str]:
    """Validate and normalise due_date; return None if invalid."""
    if not raw or str(raw).lower() in ("null", "none", ""):
        return None
    try:
        # Accept YYYY-MM-DD only
        d = date.fromisoformat(str(raw).strip())
        return d.isoformat()
    except ValueError:
        logger.debug(f"LLM returned invalid due_date: {raw!r} — ignoring")
        return None


def _validate_tasks(raw: list[dict]) -> list[dict]:
    """Ensure each task has valid text, category, and optional due_date."""
    valid_cats = {"Work", "Groceries", "Personal", "Other"}
    result = []
    for item in raw:
        text = str(item.get("text", "")).strip()
        if not text or len(text) > 500:
            continue
        cat = item.get("category", "Other")
        if cat not in valid_cats:
            cat = "Other"
        due_date = _validate_due_date(item.get("due_date"))
        result.append({"text": text, "category": cat, "due_date": due_date})
    return result


async def extract_tasks(raw_text: str) -> list[dict]:
    """
    Main entry point: try Groq first, fall back to Gemini.
    Returns validated list of {text, category, due_date} dicts.
    Raises ValueError if both APIs fail or no key is configured.
    """
    if not raw_text.strip():
        return []

    # Groq primary
    tasks = await _call_groq(raw_text)
    if tasks is not None:
        return _validate_tasks(tasks)

    # Gemini fallback
    tasks = await _call_gemini(raw_text)
    if tasks is not None:
        return _validate_tasks(tasks)

    raise ValueError("Both LLM APIs failed or no API keys configured. Check GROQ_API_KEY in .env")
