"""
ai_translator.py — OWNED BY: Sadiq (AI Integration)
=======================================================

AITranslator calls the Gemini API to rewrite dense FDA label text in
plain, everyday language. If the main (native) Gemini call is rejected
with a 401 auth error, it retries once on Gemini's OpenAI-compatible
endpoint using the same key.

Bug fixed: `_extract_text` used to be a @staticmethod but read
`self._response_mode`, which crashed with NameError. It is now a normal
method that takes `self`.
"""

from __future__ import annotations

import json
from typing import Callable, cast

from models import AITranslationError
from st_compat import RequestException, _HTTPResponse, requests


class AITranslator:
    """Calls the Gemini API to rewrite medical text in plain language."""

    API_URL_TEMPLATE: str = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )
    OPENAI_API_URL: str = (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )

    def __init__(self, api_key: str, model: str = "gemini-3.8-flash"):
        if not api_key:
            raise AITranslationError("No Gemini API key was provided.")
        self.api_key: str = api_key.strip().strip("\"'")
        self.model: str = model
        self._response_mode: str = "native"

    @staticmethod
    def _to_openai_messages(contents: list[dict[str, object]]) -> list[dict[str, str]]:
        """Convert Gemini generateContent turns to OpenAI-compatible messages."""
        messages: list[dict[str, str]] = []
        for item in contents:
            role = str(item.get("role", "user"))
            if role == "model":
                role = "assistant"
            parts = item.get("parts", [])
            text_value = ""
            if isinstance(parts, list) and parts:
                first = parts[0]
                if isinstance(first, dict):
                    candidate = first.get("text")
                    if isinstance(candidate, str):
                        text_value = candidate
            if text_value:
                messages.append({"role": role, "content": text_value})
        return messages

    def _post(self, contents: list[dict[str, object]]) -> _HTTPResponse:
        """Call Gemini using native API-key auth, with a compatibility fallback.

        Native generateContent uses x-goog-api-key. Some current AQ-format
        authorization keys can return 401 on the native gateway; the official
        OpenAI-compatible Gemini endpoint accepts the same key as a Bearer
        token, so retry there only when native authentication is rejected.
        """
        native_url = self.API_URL_TEMPLATE.format(model=self.model)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        native_payload = {"contents": contents}

        try:
            response: _HTTPResponse = cast(Callable[..., _HTTPResponse], requests.post)(
                native_url,
                headers=headers,
                data=json.dumps(native_payload),
                timeout=20,
            )
        except RequestException as exc:
            raise AITranslationError(f"Could not reach Gemini API: {exc}") from exc

        if response.ok:
            self._response_mode = "native"
            return response

        if response.status_code != 401:
            raise AITranslationError(
                f"Gemini API returned status {response.status_code}: {response.text[:300]}"
            )

        # Fallback for current AQ/auth-key gateway compatibility issues.
        openai_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        openai_payload = {
            "model": self.model,
            "messages": self._to_openai_messages(contents),
        }
        try:
            fallback: _HTTPResponse = cast(Callable[..., _HTTPResponse], requests.post)(
                self.OPENAI_API_URL,
                headers=openai_headers,
                data=json.dumps(openai_payload),
                timeout=20,
            )
        except RequestException as exc:
            raise AITranslationError(f"Could not reach Gemini compatibility API: {exc}") from exc

        if not fallback.ok:
            raise AITranslationError(
                "Gemini authentication failed on both API endpoints. "
                f"Native: {response.status_code}; compatibility: "
                f"{fallback.status_code}: {fallback.text[:250]}"
            )

        self._response_mode = "openai"
        return fallback

    def _extract_text(self, response: _HTTPResponse) -> str:
        """Pull the first candidate's text out of a generateContent
        response. Used by simplify() so the (fairly deep)
        response-shape validation only lives in one place.
        """
        try:
            response_payload = response.json()
        except ValueError as exc:
            raise AITranslationError("Gemini API returned an unexpected response.") from exc

        if not isinstance(response_payload, dict):
            raise AITranslationError("Gemini API returned an unexpected response.")

        payload_dict = cast(dict[str, object], response_payload)

        if self._response_mode == "openai":
            choices = payload_dict.get("choices")
            if not isinstance(choices, list) or not choices:
                raise AITranslationError("Gemini compatibility API returned an unexpected response.")
            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                raise AITranslationError("Gemini compatibility API returned an unexpected response.")
            message = first_choice.get("message")
            if not isinstance(message, dict):
                raise AITranslationError("Gemini compatibility API returned an unexpected response.")
            text_value = message.get("content")
            if not isinstance(text_value, str):
                raise AITranslationError("Gemini compatibility API returned an unexpected response.")
            return text_value.strip()

        candidates = payload_dict.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise AITranslationError("Gemini API returned an unexpected response.")

        first_candidate = cast(list[object], candidates)[0]
        if not isinstance(first_candidate, dict):
            raise AITranslationError("Gemini API returned an unexpected response.")

        candidate_dict = cast(dict[str, object], first_candidate)
        content = candidate_dict.get("content")
        if not isinstance(content, dict):
            raise AITranslationError("Gemini API returned an unexpected response.")

        content_dict = cast(dict[str, object], content)
        parts = content_dict.get("parts")
        if not isinstance(parts, list) or not parts:
            raise AITranslationError("Gemini API returned an unexpected response.")

        first_part = cast(list[object], parts)[0]
        if not isinstance(first_part, dict):
            raise AITranslationError("Gemini API returned an unexpected response.")

        part_dict = cast(dict[str, object], first_part)
        text_value = part_dict.get("text")
        if not isinstance(text_value, str):
            raise AITranslationError("Gemini API returned an unexpected response.")

        return text_value.strip()

    def simplify(self, text: str, section_name: str) -> str:
        """Rewrite one section of drug info in everyday language."""
        if not text:
            return "No information was provided by the FDA for this section."

        prompt = (
            "You are helping a patient with no medical background understand "
            f"their medication. Rewrite the following '{section_name}' section "
            "from an official FDA drug label in simple, clear, everyday "
            "language. Keep it accurate, use short sentences, and avoid "
            "jargon. Limit your answer to about 120 words.\n\n"
            f"Original text:\n{text}"
        )

        contents: list[dict[str, object]] = [{"role": "user", "parts": [{"text": prompt}]}]
        response = self._post(contents)
        return self._extract_text(response)
