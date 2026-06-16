"""Gemini parsing of Form 990 PDFs (rewrite of the validated legacy approach).

Extracts total revenue and every compensated individual from Part VII
with the three compensation columns kept separate:
  D - reportable compensation from the organization (the benchmark figure)
  E - reportable compensation from related organizations
  F - other compensation / estimated benefits

`process_response` is pure; the Gemini transport is injectable so tests
never touch the real API. A failed parse is an error for the caller to
record — there is no OCR fallback.
"""

import json
import time
from collections.abc import Callable

from pydantic import ValidationError

from nonprofit_benchmark.extraction import ExecutiveRecord, FilingExtraction

__all__ = [
    "ExecutiveRecord",
    "FilingExtraction",
    "GeminiParseError",
    "GeminiParser",
    "process_response",
]

GEMINI_MODEL = "gemini-2.5-flash"

PROMPT = """\
You are analyzing a nonprofit Form 990 (or 990-EZ) tax filing PDF.

Extract:
1. Total revenue (Part I line 12 on Form 990; Part I line 9 on 990-EZ).
2. Every individual listed in Part VII Section A (officers, directors,
   trustees, key employees, highest compensated employees), with the three
   compensation columns kept SEPARATE:
   - column D: reportable compensation from the organization
   - column E: reportable compensation from related organizations
   - column F: estimated other compensation from the organization and related organizations
   (On 990-EZ, use the corresponding officer compensation columns.)

Respond with ONLY this JSON structure:
{
    "total_revenue": <number or null>,
    "executives": [
        {"name": "<name>", "title": "<title or null>",
         "compensation_org": <number or null>,
         "compensation_related": <number or null>,
         "compensation_other": <number or null>}
    ]
}

Rules:
- Plain numbers only: no dollar signs, commas, or text.
- Include every listed individual, even those with zero compensation.
- NEVER sum compensation across individuals or columns.
- Use null for any value you cannot find. Use [] if Part VII lists no one.
"""


class GeminiParseError(Exception):
    """The model's answer was unusable; record the filing as failed."""


class GeminiParser:
    """Parses 990 PDFs via Gemini with retry; transport is injectable."""

    def __init__(
        self,
        generate: Callable[[bytes, str], str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
    ):
        self._generate = generate or _default_generate
        self._sleep = sleep
        self._max_retries = max_retries

    def parse(self, pdf_bytes: bytes) -> FilingExtraction:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return process_response(self._generate(pdf_bytes, PROMPT))
            except GeminiParseError:
                raise  # the model answered; a retry won't change the document
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    self._sleep(2**attempt)
        raise GeminiParseError(
            f"Gemini transport failed after {self._max_retries + 1} attempts: {last_error}"
        ) from last_error


def _default_generate(pdf_bytes: bytes, prompt: str) -> str:
    """Thin I/O shell: upload the PDF via the Gemini File API and prompt it."""
    import os
    import tempfile

    import google.generativeai as genai

    genai.configure(api_key=os.environ["GOOGLE_AI_API_KEY"])
    model = genai.GenerativeModel(GEMINI_MODEL)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(pdf_bytes)
    try:
        uploaded = genai.upload_file(path=temp_file.name, mime_type="application/pdf")
    finally:
        os.unlink(temp_file.name)
    try:
        return model.generate_content([prompt, uploaded]).text
    finally:
        try:
            genai.delete_file(uploaded.name)
        except Exception:
            pass


def process_response(response_text: str) -> FilingExtraction:
    """Pure: pull the JSON object out of a model response and validate it."""
    start = response_text.find("{")
    end = response_text.rfind("}") + 1
    if start == -1 or end <= start:
        raise GeminiParseError("No JSON object in Gemini response")
    try:
        return FilingExtraction(**json.loads(response_text[start:end]))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise GeminiParseError(f"Unusable Gemini response: {exc}") from exc
