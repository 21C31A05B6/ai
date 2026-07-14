"""
Core AI decision logic using Groq LLM.

- Uses Groq's fast LLaMA model for natural conversation responses.
- Falls back to FAQ keyword matching if Groq is unavailable.
- Detects when a caller wants a human transfer.
"""

import os
import re

from dotenv import load_dotenv

load_dotenv()

from app.faq_data import FAQS, TRANSFER_KEYWORDS, NOT_UNDERSTOOD, GREETING

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Lazy-init so import never fails even if groq isn't installed
_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=GROQ_API_KEY)
        except Exception as e:
            print(f"[AI] Groq client init failed: {e}")
    return _groq_client


# ---------------------------------------------------------------------------
# Transfer detection
# ---------------------------------------------------------------------------

def wants_human(user_text: str) -> bool:
    text = user_text.lower()
    return any(kw in text for kw in TRANSFER_KEYWORDS)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(business_type: str = "company") -> str:
    # Build a compact FAQ reference so Groq knows what the business does
    faqs = FAQS.get(business_type, FAQS.get("company", []))
    faq_lines = "\n".join(
        f"- {', '.join(kws)}: {ans}"
        for kws, ans in faqs
    )
    return (
        "You are a professional AI phone assistant for a company's interview and hiring support line. "
        "Answer callers in a friendly, clear, and concise manner — as if speaking on the phone. "
        "Keep responses under 3 sentences. Do NOT use bullet points or markdown. "
        "If you don't know, say so politely and offer to connect to HR. "
        "If the caller asks for a human, manager, or is angry, do NOT answer their question — "
        "just say 'Please hold while I transfer your call.' and nothing else.\n\n"
        "Business context (use this to answer factual questions):\n"
        f"{faq_lines}"
    )


# ---------------------------------------------------------------------------
# Groq LLM answer
# ---------------------------------------------------------------------------

def get_groq_answer(business_type: str, user_text: str, history: list = None) -> str:
    """
    Call Groq with conversation history for multi-turn awareness.
    `history` is a list of {"role": "user"|"assistant", "content": "..."} dicts.
    """
    client = _get_groq_client()
    if client is None:
        raise RuntimeError("Groq client not available — check GROQ_API_KEY in .env")

    messages = [{"role": "system", "content": _build_system_prompt(business_type)}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.6,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# FAQ fallback
# ---------------------------------------------------------------------------

def _faq_answer(business_type: str, user_text: str) -> tuple[str, bool]:
    faqs = FAQS.get(business_type, FAQS.get("company", []))
    best_score = 0
    best_answer = None
    text_lower = user_text.lower()
    for keywords, answer in faqs:
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_answer = answer
    if best_score == 0 or best_answer is None:
        return NOT_UNDERSTOOD, False
    return best_answer, True


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_answer(business_type: str, user_text: str, history: list = None):
    """
    Returns (answer_text, matched: bool).

    Tries Groq first (fast, natural language).
    Falls back to FAQ keyword matching if Groq fails.
    """
    if GROQ_API_KEY:
        try:
            answer = get_groq_answer(business_type, user_text, history)
            return answer, True
        except Exception as exc:
            print(f"[AI] Groq error, using FAQ fallback: {exc}")

    return _faq_answer(business_type, user_text)
