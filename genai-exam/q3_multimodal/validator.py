"""JSON syntax extraction + strict schema validation for model output.

Two separate jobs, deliberately kept apart:

1. ``extract_json``      - can we even find a JSON object in the model reply?
                           (models sometimes wrap JSON in ```json fences or add prose)
2. ``validate_analysis`` - does that object satisfy the Q.3 schema exactly?

Important: passing validation only proves the *structure* is correct. It says
nothing about whether the description matches the image. Truth is checked by
evaluator.py and by a human - never by this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from prompts import ANALYSIS_FIELDS

MAX_TEXT_LEN = 6000          # guard against absurdly long single fields
EVENT_KEYS = set(ANALYSIS_FIELDS)


class JSONExtractionError(ValueError):
    """Raised when no parseable JSON object can be found in a model reply."""


@dataclass
class ValidationResult:
    """Outcome of validating one analysis dict."""

    valid: bool
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict | None = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "status": "valid" if self.valid else "invalid",
            "errors": self.errors,
            "error_count": len(self.errors),
            "warnings": self.warnings,
            "warning_count": len(self.warnings),
            "checked_rules": list(SCHEMA_RULES),
            "note": (
                "Schema validation checks JSON syntax, field names, types and non-empty text. "
                "It does NOT prove that the description matches the image."
            ),
        }


SCHEMA_RULES = (
    "six required top-level fields present",
    "no unexpected top-level fields",
    "detailed_description is a non-empty string",
    "objects is an array of {name, attributes, evidence}",
    "object.name is a non-empty string",
    "object.attributes is an array of strings",
    "object.evidence is a string",
    "activities is an array of strings",
    "caption is a non-empty string",
    "summary is a non-empty string",
    "uncertainties is an array of strings",
)

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json(raw_text: str) -> Any:
    """Return the first JSON value found in ``raw_text``.

    Handles ```json fenced blocks, leading prose and trailing commentary. Raises
    ``JSONExtractionError`` (never a bare ``json.JSONDecodeError``) so callers can
    convert it into a clean HTTP 422 response.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise JSONExtractionError("The model returned an empty response.")

    candidates: list[str] = []
    fenced = _FENCE_RE.search(raw_text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(raw_text.strip())

    decoder = json.JSONDecoder()
    for candidate in candidates:
        for start in _brace_positions(candidate):
            try:
                value, _end = decoder.raw_decode(candidate[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, (dict, list)):
                return value

    snippet = raw_text.strip()[:200].replace("\n", " ")
    raise JSONExtractionError(f"No valid JSON object found in the model response. First 200 characters: {snippet!r}")


def _brace_positions(text: str) -> list[int]:
    return [i for i, ch in enumerate(text) if ch in "{["][:20]


# ----------------------------------------------------------------- validate --
def validate_analysis(data: Any) -> ValidationResult:
    """Validate ``data`` against the Q.3 analysis schema. Never raises."""
    errors: list[dict] = []
    warnings: list[str] = []

    def err(field_path: str, message: str) -> None:
        errors.append({"field": field_path, "message": message})

    if not isinstance(data, dict):
        err("$", f"Top-level JSON must be an object, received {type(data).__name__}.")
        return ValidationResult(False, errors, warnings, None)

    # 1. required top-level fields
    for key in ANALYSIS_FIELDS:
        if key not in data:
            err(key, "Required top-level field is missing.")

    # 2. no unexpected top-level fields
    for key in data:
        if key not in EVENT_KEYS:
            err(key, "Unexpected top-level field is not allowed by the schema.")

    if errors:
        # further checks would only produce noise once the shape is wrong
        return ValidationResult(False, errors, warnings, None)

    normalized: dict = {}

    # 3. string fields
    for key in ("detailed_description", "caption", "summary"):
        value = data[key]
        if not isinstance(value, str):
            err(key, f"Must be a string, received {type(value).__name__}.")
        elif not value.strip():
            err(key, "Must be a non-empty string.")
        elif len(value) > MAX_TEXT_LEN:
            err(key, f"Must be shorter than {MAX_TEXT_LEN} characters.")
        else:
            normalized[key] = value.strip()

    # 4. objects
    objects = data["objects"]
    if not isinstance(objects, list):
        err("objects", f"Must be an array, received {type(objects).__name__}.")
    else:
        cleaned_objects = []
        for index, item in enumerate(objects):
            path = f"objects[{index}]"
            if not isinstance(item, dict):
                err(path, f"Must be an object with name/attributes/evidence, received {type(item).__name__}.")
                continue
            for required in ("name", "attributes", "evidence"):
                if required not in item:
                    err(f"{path}.{required}", "Required field is missing.")
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                err(f"{path}.name", "Must be a non-empty string.")
            attributes = item.get("attributes")
            if not isinstance(attributes, list):
                err(f"{path}.attributes", f"Must be an array of strings, received {type(attributes).__name__}.")
            elif any(not isinstance(a, str) for a in attributes):
                err(f"{path}.attributes", "Every attribute must be a string.")
            elif not attributes:
                warnings.append(f"{path}.attributes is empty - the object is listed without any visible attribute.")
            evidence = item.get("evidence")
            if not isinstance(evidence, str):
                err(f"{path}.evidence", f"Must be a string, received {type(evidence).__name__}.")
            elif not evidence.strip():
                err(f"{path}.evidence", "Must be a non-empty string.")
            elif len(evidence.strip()) < 15:
                warnings.append(f"{path}.evidence is very short, so it is weak evidence for the object.")
            extra = set(item) - {"name", "attributes", "evidence"}
            if extra:
                warnings.append(f"{path} contains extra keys {sorted(extra)}; the schema only defines name/attributes/evidence.")
            if isinstance(name, str) and isinstance(attributes, list) and isinstance(evidence, str):
                cleaned_objects.append(
                    {
                        "name": name.strip(),
                        "attributes": [a.strip() for a in attributes if isinstance(a, str)],
                        "evidence": evidence.strip(),
                    }
                )
        if len(cleaned_objects) != len(objects):
            errors.append({"field": "objects", "message": "One or more object entries are invalid."})
        else:
            normalized["objects"] = cleaned_objects
            if not cleaned_objects:
                warnings.append("objects is empty - either the image really shows nothing nameable or the model missed objects.")

    # 5. arrays of strings
    for key in ("activities", "uncertainties"):
        value = data[key]
        if not isinstance(value, list):
            err(key, f"Must be an array of strings, received {type(value).__name__}.")
        elif any(not isinstance(item, str) for item in value):
            err(key, "Every item must be a string.")
        else:
            cleaned = [item.strip() for item in value if item.strip()]
            # silently dropping "  " entries is a normalisation, so record it as a warning
            if len(cleaned) != len(value):
                warnings.append(f"{key} contained blank entries, which were removed during normalisation.")
            normalized[key] = cleaned

    if errors:
        return ValidationResult(False, errors, warnings, None)

    # 6. documented, non-fatal consistency warnings
    if not normalized["objects"]:
        warnings.append("No objects were reported, which is unusual for a photo or illustration.")
    if normalized["activities"]:
        if not normalized["detailed_description"]:
            pass
    else:
        warnings.append("activities is empty. This is allowed, but the evaluation stage should confirm whether the image really shows no activity.")
    if not normalized["uncertainties"] and _hedge_words(normalized["detailed_description"] + " " + normalized["summary"]):
        warnings.append(
            "The text contains hedged wording but \"uncertainties\" is empty, so the model's own uncertainty is not recorded."
        )
    if len(normalized["caption"]) > 220:
        warnings.append("caption is long for a caption (more than 220 characters).")

    return ValidationResult(True, errors, warnings, normalized)


def _hedge_words(text: str) -> bool:
    lowered = f" {text.lower()} "
    hedges = (" appear", " appears", " seems", " likely", " possibly", " probably", " may be",
              " might be", " unclear", " uncertain", " suggests", " perhaps", " roughly", " approximately")
    return any(hedge in lowered for hedge in hedges)
