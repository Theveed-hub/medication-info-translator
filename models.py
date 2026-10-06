"""
models.py — OWNED BY: Person 1 (Domain Model & Input Validation)
==================================================================

The custom exception hierarchy plus the `Medication` dataclass:
validating a user-typed drug name, cleaning FDA-label boilerplate with
regex, and turning a raw openFDA JSON result into a typed object.

No Streamlit or network code lives here on purpose — this module is
pure logic, so it's the easiest one in the whole app to unit test in
isolation (no mocking required).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar, cast


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class MedSimplifyError(Exception):
    """Base class for all app-specific errors."""


class InvalidMedicationNameError(MedSimplifyError):
    """Raised when the user's input fails basic validation."""


class MedicationNotFoundError(MedSimplifyError):
    """Raised when the openFDA label API returns no results."""


class FDANetworkError(MedSimplifyError):
    """Raised when a request to openFDA fails at the network/HTTP level."""


class AITranslationError(MedSimplifyError):
    """Raised when the Gemini API call fails or returns an unusable response."""


# ---------------------------------------------------------------------------
# Medication (OOP + regex)
# ---------------------------------------------------------------------------

@dataclass
class Medication:
    """Represents a single medication's parsed label data."""

    name: str
    generic_name: str = ""
    brand_names: list[str] = field(default_factory=list)
    usage: str = ""
    warnings: str = ""
    side_effects: str = ""
    dosage: str = ""
    raw: dict[str, object] = field(default_factory=dict)

    # --- regex-based text cleaning -----------------------------------
    # FIX: these must be ClassVar, otherwise @dataclass turns them into
    # constructor parameters / instance attributes and pollutes
    # __init__, __repr__ and __eq__ with regex objects.
    _CITATION_RE: ClassVar[re.Pattern[str]] = re.compile(r"\(\d+(\.\d+)*\)")  # e.g. "(2.1)"
    _WHITESPACE_RE: ClassVar[re.Pattern[str]] = re.compile(r"\s+")
    _BULLET_RE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*[\u2022\-\*]\s*", re.MULTILINE)
    _NAME_VALIDATION_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^[A-Za-z0-9\s\-/]+$"
    )

    # A handful of clinically meaningful phrases we want to surface as
    # "keywords" to the user even before AI simplification.
    _WARNING_KEYWORD_PATTERNS: ClassVar[list[str]] = [
        r"do not use\b[^.]*",
        r"may cause\b[^.]*",
        r"risk of\b[^.]*",
        r"stop use and ask a doctor\b[^.]*",
        r"contraindicat\w*[^.]*",
        r"serious side effects?\b[^.]*",
        r"ask a doctor before use\b[^.]*",
        r"overdose\b[^.]*",
    ]

    @classmethod
    def validate_name(cls, name: str) -> str:
        """Validate and normalize a user-supplied medication name.

        Raises InvalidMedicationNameError on empty or malformed input.
        """
        cleaned = name.strip()
        if not cleaned:
            raise InvalidMedicationNameError("Medication name cannot be empty.")
        if len(cleaned) > 100:
            raise InvalidMedicationNameError("Medication name is too long.")
        if not cls._NAME_VALIDATION_RE.match(cleaned):
            raise InvalidMedicationNameError(
                "Medication name may only contain letters, numbers, spaces, hyphens, and slashes."
            )
        return cleaned

    @classmethod
    def clean_text(cls, text: str | list[str] | None) -> str:
        """Strip FDA-label boilerplate (citation markers, bullets, extra
        whitespace) from a raw label field using regular expressions."""
        if not text:
            return ""
        if isinstance(text, list):
            text = " ".join(text)
        text = cls._CITATION_RE.sub("", text)
        text = cls._BULLET_RE.sub("", text)
        text = cls._WHITESPACE_RE.sub(" ", text)
        return text.strip()

    @classmethod
    def from_openfda_result(cls, name: str, result: dict[str, object]) -> "Medication":
        """Build a Medication instance from one openFDA label API result."""
        openfda_value = result.get("openfda", {})
        openfda: dict[str, object] = {}
        if isinstance(openfda_value, dict):
            raw_openfda = cast(dict[object, object], openfda_value)
            openfda = {
                str(key): value
                for key, value in raw_openfda.items()
                if isinstance(key, str)
            }

        def text_field(key: str) -> str | list[str] | None:
            value = result.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                list_values = cast(list[object], value)
                return [item for item in list_values if isinstance(item, str)]
            return None

        def string_list_field(key: str) -> list[str]:
            value = openfda.get(key)
            if isinstance(value, list):
                list_values = cast(list[object], value)
                return [item for item in list_values if isinstance(item, str)]
            return []

        generic_names = string_list_field("generic_name")
        brand_names = string_list_field("brand_name")
        warnings = text_field("warnings") or text_field("warnings_and_cautions")

        return cls(
            name=name,
            generic_name=", ".join(generic_names) or name,
            brand_names=brand_names,
            usage=cls.clean_text(text_field("indications_and_usage")),
            warnings=cls.clean_text(warnings),
            side_effects=cls.clean_text(text_field("adverse_reactions")),
            dosage=cls.clean_text(text_field("dosage_and_administration")),
            raw=result,
        )

    def extract_warning_keywords(self) -> list[str]:
        """Use regex to pull short, human-readable warning snippets out of
        the raw warnings text (in addition to the AI-simplified version)."""
        if not self.warnings:
            return []
        found: list[str] = []
        for pattern in self._WARNING_KEYWORD_PATTERNS:
            raw_matches: list[str] = re.findall(pattern, self.warnings, flags=re.IGNORECASE)
            for match in raw_matches:
                snippet = match.strip()
                if snippet and snippet not in found:
                    found.append(snippet[:160])
        return found[:8]

    def has_missing_fields(self) -> list[str]:
        """Report which key sections came back empty from the API."""
        missing: list[str] = []
        # FIX: renamed loop variable so it doesn't shadow the `field`
        # imported from dataclasses used above in this same class body.
        for attr_name in ("usage", "warnings", "side_effects", "dosage"):
            if not getattr(self, attr_name):
                missing.append(attr_name)
        return missing
