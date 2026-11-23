import json

import httpx

from server.core.config import settings
from server.models.document import FIELD_NAMES


class GroqNotConfigured(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class GroqRequestFailed(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


SYSTEM_PROMPT = """You extract compliance facts from the document text the user provides.
Return a JSON object with a "fields" array of exactly six objects.
Each object has field_name, value, confidence, page_number, and source_excerpt.

field_name must be one of:
act_regulation_name, applicable_state, industry, registration_licence_type, validity_renewal_details, key_compliance_requirements.

Rules:
- Use only the document text. Do not add facts from general knowledge.
- If the text does not support a field, set value, page_number, and source_excerpt to null and confidence to 0.
- confidence is an integer from 0 to 100.
- source_excerpt must be a short quote copied from the document, from the same page as the value.
- page_number must be the integer shown in that quote's [Page N] marker.
- Include every field_name exactly once.
"""


def extract_fields(document_text: str) -> list[dict]:
    if not settings.groq_api_key:
        raise GroqNotConfigured("GROQ_API_KEY is not configured")
    if not settings.groq_model:
        raise GroqNotConfigured("GROQ_MODEL is not configured")

    payload = {
        "model": settings.groq_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": document_text},
        ],
    }
    try:
        response = httpx.post(
            f"{settings.groq_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        raise GroqRequestFailed("The extraction service rejected the request") from exc
    except Exception as exc:
        raise GroqRequestFailed("The extraction service could not be reached") from exc

    return _parse_fields(content, document_text)


def _parse_fields(content: str, document_text: str) -> list[dict]:
    try:
        parsed = json.loads(_strip_fence(content))
        raw_fields = parsed["fields"] if isinstance(parsed, dict) else parsed
        by_name = {item["field_name"]: item for item in raw_fields}
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise GroqRequestFailed("The extraction response could not be read") from exc

    corpus = document_text.casefold()
    fields: list[dict] = []
    for name in FIELD_NAMES:
        item = by_name.get(name) or {}
        value = _clean_text(item.get("value"))
        excerpt = _clean_text(item.get("source_excerpt"))
        page_number = _clean_page(item.get("page_number"))
        confidence = _clean_confidence(item.get("confidence"))
        if value is None or excerpt is None or excerpt.casefold() not in corpus:
            value = None
            excerpt = None
            page_number = None
            confidence = 0
        fields.append(
            {
                "field_name": name,
                "value": value,
                "confidence": confidence,
                "page_number": page_number,
                "source_excerpt": excerpt[:500] if excerpt else None,
            }
        )
    return fields


def _strip_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _clean_page(value: object) -> int | None:
    number = _whole_number(value)
    if number is None or number < 1:
        return None
    return number


def _clean_confidence(value: object) -> int:
    number = _whole_number(value)
    if number is None:
        return 0
    return max(0, min(100, number))


def _whole_number(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return int(value)
