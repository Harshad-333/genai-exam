"""Prompt engineering for the multimodal image-understanding system.

This module is the single place where every prompt lives, so the interactive
"Prompt Engineering" tab of the UI, the live provider calls and the docs all
show exactly the same text.

Three prompt variants are kept on purpose and compared in the UI and in
docs/PROMPT_DESIGN.md:

* ``BASIC_PROMPT``     - one-liner, no schema, no honesty rules (the "before")
* ``BASE_PROMPT``      - the required careful-analysis instruction (the "after")
* ``STRUCTURED_PROMPT``- BASE_PROMPT + the exact JSON contract + field rules

A prompt can make output *consistently shaped* and *less likely* to invent
facts. It cannot guarantee factual correctness - that is what validator.py and
evaluator.py are for, and the docs say so explicitly.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# 1. The base prompt required by the assignment (verbatim).
# ---------------------------------------------------------------------------
BASE_PROMPT = (
    "You are a careful multimodal image-understanding assistant. Analyze the supplied image and "
    "describe only visual information supported by the image. Identify important objects, visible "
    "attributes, spatial relationships, and activities. Generate a detailed description, object "
    "list, activity list, concise caption, and short summary. Distinguish observations from "
    "interpretations. Do not invent identities, locations, intentions, unreadable text, or "
    "background facts. Mark uncertain details explicitly. Return valid JSON matching the required "
    "schema."
)

# ---------------------------------------------------------------------------
# 2. A deliberately weak prompt, kept for the comparison table (Prompt v0).
# ---------------------------------------------------------------------------
BASIC_PROMPT = "Describe this image. Give objects, activities, a caption and a summary as JSON."

# ---------------------------------------------------------------------------
# 3. The JSON contract, exactly as required by the assignment.
# ---------------------------------------------------------------------------
ANALYSIS_FIELDS: tuple[str, ...] = (
    "detailed_description",
    "objects",
    "activities",
    "caption",
    "summary",
    "uncertainties",
)

JSON_EXAMPLE: dict = {
    "detailed_description": "Description of the visible image",
    "objects": [
        {
            "name": "Laptop",
            "attributes": ["open"],
            "evidence": "A laptop is visibly present in the image.",
        }
    ],
    "activities": [],
    "caption": "A concise image caption.",
    "summary": "A short summary of the image.",
    "uncertainties": [],
}

FIELD_RULES = """
Field rules (the response is rejected if any of these is violated):
1.  "detailed_description": non-empty string. 3-6 sentences, only visible facts.
2.  "objects": array. Each item is an object with exactly:
      "name"       - non-empty string (the object category, e.g. "laptop"),
      "attributes" - array of strings, the visible properties only (e.g. ["open", "silver"]),
      "evidence"   - string saying where/how the object is visible in the image.
3.  "activities": array of strings. Use [] when no activity is clearly visible.
4.  "caption": non-empty string, one short line (roughly 8-16 words).
5.  "summary": non-empty string, 1-2 sentences.
6.  "uncertainties": array of strings. Every hedged statement ("appears", "possibly",
    "unclear") MUST also be listed here. Use [] only when nothing is uncertain.
7.  Exactly the six top-level keys above. No extra keys, no markdown, no commentary.
""".strip()

STRUCTURED_PROMPT = (
    f"{BASE_PROMPT}\n\n"
    "Return one JSON object with exactly these six top-level fields:\n\n"
    f"{json.dumps(JSON_EXAMPLE, indent=2)}\n\n"
    f"{FIELD_RULES}\n\n"
    "Return the JSON object and nothing else."
)

# ---------------------------------------------------------------------------
# 4. Machine-readable schema handed to providers that support structured
#    output (Google Gemini ``response_schema``). Kept in sync with validator.py.
# ---------------------------------------------------------------------------
GEMINI_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "detailed_description": {"type": "string"},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "attributes": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "attributes", "evidence"],
            },
        },
        "activities": {"type": "array", "items": {"type": "string"}},
        "caption": {"type": "string"},
        "summary": {"type": "string"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": list(ANALYSIS_FIELDS),
}

# ---------------------------------------------------------------------------
# 5. Prompt used when a *second* model is asked to review an analysis
#    (optional feature, live mode only - see evaluator.py).
# ---------------------------------------------------------------------------
SECOND_OPINION_PROMPT = (
    "You are a reviewing assistant. You receive (a) an image and (b) a JSON analysis produced by "
    "another model. Compare them and report only statements in the analysis that are NOT clearly "
    "supported by the image, plus clearly visible things the analysis missed. "
    "Return JSON: {\"concerns\": [{\"statement\": \"...\", \"category\": "
    "\"unsupported_claim|possible_error|possible_omission|uncertain_detail\", "
    "\"explanation\": \"...\", \"suggested_correction\": \"...\"}], \"verified_ok\": [\"...\"]}. "
    "Your own output is a second opinion, not ground truth: it also needs human verification."
)

# ---------------------------------------------------------------------------
# 6. Comparison used by the UI and PROMPT_DESIGN.md
# ---------------------------------------------------------------------------
PROMPT_COMPARISON: list[dict[str, str]] = [
    {
        "aspect": "Instruction given",
        "basic": '"Describe this image." One sentence, no output contract.',
        "structured": "Role, honesty rules, object/activity/spatial requirements, explicit JSON contract.",
    },
    {
        "aspect": "Output shape",
        "basic": "Free-form text; JSON only if the model happens to comply. Keys and types drift between runs.",
        "structured": "Six fixed top-level keys, fixed nested keys and types; machine-checkable by validator.py.",
    },
    {
        "aspect": "Missing information",
        "basic": "Model usually fills every field, inventing plausible content for empty scenes.",
        "structured": 'Empty arrays allowed ("activities": [], "uncertainties": []), so silence is a legal answer.',
    },
    {
        "aspect": "Uncertainty",
        "basic": "Hedges and facts are mixed in one paragraph; no way to separate them.",
        "structured": "Hedged phrasing must be repeated in \"uncertainties\", so reviewers can see what the model is unsure about.",
    },
    {
        "aspect": "Unreadable text / identities",
        "basic": "Often reads text that is not legible and guesses names, brands or places.",
        "structured": "Explicitly forbidden to invent identities, locations, intentions or unreadable text.",
    },
    {
        "aspect": "What it does NOT fix",
        "basic": "Positions of objects may still be wrong.",
        "structured": (
            "Still can hallucinate: the JSON can be perfectly valid and still contain a wrong object. "
            "Schema validation proves structure, never truth - hence the evaluation stage."
        ),
    },
]

PROMPT_NOTES = (
    "Why explicit instructions help: a fixed schema removes format ambiguity, so the same question "
    "returns the same shape every time and can be validated automatically; telling the model that "
    "empty arrays are acceptable removes the pressure to invent content; requiring hedges to be "
    "repeated in \"uncertainties\" makes uncertainty visible to the reader; and forbidding invented "
    "identities, locations or text removes the most common hallucination triggers. "
    "Prompts reduce hallucinations but cannot eliminate them: a language model generates the most "
    "plausible text, not a verified measurement of the pixels. That is why this project validates "
    "the JSON (structure) and then evaluates the content against the actual image (meaning)."
)
