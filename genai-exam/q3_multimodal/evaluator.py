"""Evaluation of an analysis against the actual image.

Two independent sources of findings are combined:

1. **Automatic text heuristics** (``heuristic_findings``) - deterministic checks
   that can be verified by a program alone: is a hedged phrase recorded in
   "uncertainties"?, does the description mention every object it lists?, does
   the caption share any content word with the description?, does the analysis
   claim readable text or a mental state? These findings are software-checkable,
   which is why they can be unit-tested.

2. **Curated sample comparison** (``samples.SAMPLES[*]["curated_findings"]``) -
   a manual, image-by-image comparison of the sample analysis with the sample
   image (including a human ground-truth list). This is what a student or
   examiner does with their own eyes; the app stores it so the evaluation screen
   is populated in Offline Demo Mode.

Neither source is ground truth on its own: the UI lets a human confirm, reject or
edit every finding, and a second AI model (optional, live mode only) can add its
own opinion, which is explicitly labelled as *not* independent ground truth.
"""

from __future__ import annotations

import re

CATEGORIES: dict[str, str] = {
    "correct": "Correct observation",
    "error": "Possible error",
    "omission": "Possible omission",
    "unsupported": "Unsupported claim",
    "uncertain": "Uncertain detail",
}

VERIFICATION_STATUSES: dict[str, str] = {
    "pending": "Needs manual review",
    "confirmed": "Confirmed by reviewer",
    "rejected": "Rejected by reviewer",
    "edited": "Edited by reviewer",
}

CATEGORY_LABELS = list(CATEGORIES.values())

HEDGES = ("appears", "appear", "seems", "possibly", "probably", "likely", "may be", "might be",
          "unclear", "uncertain", "suggests", "perhaps", "roughly", "approximately")

EMOTION_WORDS = ("smiling", "happy", "sad", "angry", "tired", "excited", "concentrating",
                 "enjoying", "relaxed", "bored", "worried", "feeling")

TEXT_CLAIM_PATTERNS = (
    r"reads?[\s\"']", r"reading[\s\"']", r"says[\s\"']", r"that says", r"labelled[\s\"']?",
    r"labeled[\s\"']?", r"text[\s\"']?that", r"with the (?:word|text|title)",
    r"word[\s\"']", r"titled[\s\"']?", r"printed on it", r"product name",
)

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "with", "is", "are", "was", "were",
    "this", "that", "these", "those", "it", "its", "as", "by", "for", "from", "into", "be", "been",
    "image", "picture", "photo", "shows", "show", "showing", "visible", "there", "their", "them",
    "his", "her", "she", "he", "they", "you", "your", "which", "while", "also", "some", "any", "not",
}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 3 and w not in STOPWORDS]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _finding(fid: str, category: str, statement: str, visible: str, why: str,
             correction: str, source: str, confidence: str = "medium") -> dict:
    return {
        "id": fid,
        "category": category,
        "category_label": CATEGORIES[category],
        "statement": statement,
        "visible": visible,
        "why": why,
        "suggested_correction": correction,
        "verification_status": "pending",
        "verification_label": VERIFICATION_STATUSES["pending"],
        "source": source,
        "confidence": confidence,
        "reviewer_note": "",
    }


# ------------------------------------------------------- automatic checks ----
def heuristic_findings(analysis: dict) -> list[dict]:
    """Deterministic, unit-testable checks over the analysis text."""
    findings: list[dict] = []
    if not isinstance(analysis, dict):
        return findings

    description = str(analysis.get("detailed_description", ""))
    summary = str(analysis.get("summary", ""))
    caption = str(analysis.get("caption", ""))
    objects = analysis.get("objects") or []
    activities = analysis.get("activities") or []
    uncertainties = analysis.get("uncertainties") or []
    body = f"{description} {summary}"

    # 1. hedged wording that is not recorded in "uncertainties"
    if not uncertainties:
        for sentence in _sentences(description):
            low = sentence.lower()
            if any(h in low for h in HEDGES):
                findings.append(_finding(
                    "auto-hedge-1", "uncertain",
                    f"Hedged wording used without recording it: \"{sentence}\"",
                    "This is a check on the analysis text itself, not on the image: the sentence hedges, but \"uncertainties\" is empty.",
                    "The prompt requires every hedged statement to appear in \"uncertainties\" so readers can see what the model is unsure about. An empty array hides that doubt.",
                    "Move the uncertain part of the sentence into \"uncertainties\", or state the observation plainly if it is certain.",
                    "automatic check (hedge vs uncertainties)",
                ))
                break

    # 2. objects listed by the analysis but never mentioned in the description
    desc_words = set(_words(description))
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name", "")).strip()
        if not name:
            continue
        name_words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3]
        if name_words and not any(w in desc_words for w in name_words):
            findings.append(_finding(
                f"auto-obj-{name.lower().replace(' ', '-')}", "omission",
                f"Object \"{name}\" is listed in \"objects\" but does not appear in \"detailed_description\".",
                f"The analysis itself is the evidence: \"{name}\" is named in the object list with evidence \"{str(obj.get('evidence', ''))[:90]}\", but the description never mentions it.",
                "A description should mention the objects it claims to have found; otherwise the object list and the description contradict each other.",
                f"Add a sentence about the {name.lower()} to the description, or remove it from \"objects\" if it was a mistake.",
                "automatic check (object vs description)",
            ))

    # 3. activities claimed without any visible agent in the description
    if activities and not _words(description):
        findings.append(_finding(
            "auto-activity-1", "unsupported",
            f"Activity claimed without any described actor: {activities}",
            "There is no person or moving thing anywhere in the description, so nothing in the text can perform the listed activity.",
            "An activity needs a visible agent. Listing an activity with no actor is an inference about possible use, not an observation.",
            "Set \"activities\": [] or describe the visible agent of the activity.",
            "automatic check (activity vs description)",
        ))

    # 4. claims about readable text
    for pattern in TEXT_CLAIM_PATTERNS:
        match = re.search(pattern, body.lower())
        if match:
            snippet = _context(body, match.start())
            findings.append(_finding(
                "auto-text-1", "unsupported",
                f"Claim about readable text: \"{snippet}\"",
                "Readable text can only be verified by a human looking at the image (or an OCR tool); the app cannot confirm it automatically.",
                "Inventing text content ('the label says ...', 'the title reads ...') is one of the most frequent vision-language hallucinations. Without a legible-text check the claim must be treated as unverified.",
                "Remove the claimed text, or rephrase as 'the label contains text that is not legible in this image'.",
                "automatic check (text claim)",
            ))
            break

    # 5. interpretation of mental state or emotion
    for sentence in _sentences(description):
        low = sentence.lower()
        hit = next((w for w in EMOTION_WORDS if w in low), None)
        if hit:
            findings.append(_finding(
                "auto-emotion-1", "unsupported",
                f"Mental state or emotion reported: \"{sentence}\"",
                "Emotion and intention are internal states; they are not directly observable in pixels unless the face is drawn in detail.",
                f"The words \"{hit}\" describe an interpretation. The base prompt asks the model to distinguish observations from interpretations.",
                "Describe only posture and visible action, e.g. 'a person is seated facing a laptop'.",
                "automatic check (emotion/interpretation)",
            ))
            break

    # 6. objects without attributes -> detail is probably missing
    for obj in objects:
        if isinstance(obj, dict) and isinstance(obj.get("attributes"), list) and not obj["attributes"]:
            findings.append(_finding(
                f"auto-attrs-{str(obj.get('name', '')).lower().replace(' ', '-')}", "omission",
                f"No attributes recorded for \"{obj.get('name')}\".",
                f"The object is listed with evidence \"{str(obj.get('evidence', ''))[:90]}\" but with no visible attribute.",
                "The schema asks for the visible attributes of each object; an empty attributes list loses information such as colour, state or position.",
                "Add the visible attributes (colour, state, position) to the object.",
                "automatic check (empty attributes)",
            ))

    # 7. weak evidence strings
    for obj in objects:
        if isinstance(obj, dict):
            evidence = str(obj.get("evidence", "")).strip()
            if evidence and len(evidence) < 25:
                findings.append(_finding(
                    f"auto-evid-{str(obj.get('name', '')).lower().replace(' ', '-')}", "uncertain",
                    f"Weak evidence for \"{obj.get('name')}\": \"{evidence}\"",
                    "The evidence string is very short, so it does not tell the reviewer where in the image the object can be found.",
                    "Evidence is what makes a claim checkable; a short or generic sentence cannot be verified quickly.",
                    "State where the object is and what identifies it, e.g. 'a red book lies at the right of the desk'.",
                    "automatic check (evidence quality)",
                ))

    # 8. caption not grounded in the description
    if caption and description:
        caption_words = set(_words(caption))
        if caption_words and not (caption_words & desc_words):
            findings.append(_finding(
                "auto-caption-1", "error",
                f"Caption shares no content word with the description: \"{caption}\"",
                "The caption and the description are checked against each other; they describe unrelated content words.",
                "A caption summarises the same image as the description, so a complete mismatch usually means one of the two was generated loosely.",
                "Regenerate the caption from the description, or fix whichever of the two is wrong.",
                "automatic check (caption vs description)",
            ))

    return findings


def _context(text: str, index: int, width: int = 60) -> str:
    start = max(0, index - width // 2)
    return text[start:start + width].strip().replace("\n", " ")


# ------------------------------------------------------------- assembly -----
def build_evaluation(analysis: dict, sample_key: str | None = None,
                     ground_truth: list[str] | None = None, mode: str = "offline") -> dict:
    """Combine curated (sample) findings and automatic checks into one report."""
    findings: list[dict] = []

    sample = None
    if sample_key:
        from samples import get_sample  # local import keeps the modules loosely coupled

        sample = get_sample(sample_key)
        if sample:
            for item in sample["curated_findings"]:
                findings.append(_finding(
                    item["id"], item["category"], item["statement"], item["visible"],
                    item["why"], item["suggested_correction"],
                    "manual comparison of the sample analysis with the sample image (illustrative)",
                    "high",
                ))
            ground_truth = ground_truth or sample["ground_truth"]

    seen = {_norm(f["statement"]) for f in findings}
    for finding in heuristic_findings(analysis):
        if _norm(finding["statement"]) not in seen:
            findings.append(finding)
            seen.add(_norm(finding["statement"]))

    counts = {key: 0 for key in CATEGORIES}
    for finding in findings:
        counts[finding["category"]] = counts.get(finding["category"], 0) + 1

    return {
        "findings": findings,
        "counts": counts,
        "counts_labelled": {CATEGORIES[k]: v for k, v in counts.items()},
        "total": len(findings),
        "ground_truth": ground_truth or [],
        "illustrative": bool(sample is not None and sample.get("illustrative")),
        "mode": mode,
        "disclaimer": (
            "A finding is a hypothesis raised by an automatic check or by a manual comparison; "
            "it becomes a result only when a human confirms, edits or rejects it. "
            "Automatic checks can be run and tested as software, but only a human can confirm what the image really shows."
        ),
        "how_produced": (
            "Curated findings: manual comparison of the sample analysis with the sample image (Offline Demo Mode). "
            "Automatic findings: deterministic text checks in evaluator.py."
            if sample is not None else
            "Automatic findings: deterministic text checks in evaluator.py. No curated sample comparison applies to an uploaded image."
        ),
    }


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())[:120]


# ------------------------------------------------------------ manual review --
def apply_review(finding: dict, action: dict) -> dict:
    """Return a copy of ``finding`` with one reviewer action applied."""
    updated = dict(finding)
    kind = str(action.get("type", "")).lower()
    note = str(action.get("note", "")).strip()

    if kind == "confirm":
        updated["verification_status"] = "confirmed"
        updated["verification_label"] = VERIFICATION_STATUSES["confirmed"]
    elif kind == "reject":
        updated["verification_status"] = "rejected"
        updated["verification_label"] = VERIFICATION_STATUSES["rejected"]
    elif kind == "edit":
        for field_name in ("statement", "visible", "why", "suggested_correction", "category"):
            if field_name in action and str(action[field_name]).strip():
                updated[field_name] = str(action[field_name]).strip()
        if updated.get("category") in CATEGORIES:
            updated["category_label"] = CATEGORIES[updated["category"]]
        updated["verification_status"] = "edited"
        updated["verification_label"] = VERIFICATION_STATUSES["edited"]
    elif kind == "reset":
        updated["verification_status"] = "pending"
        updated["verification_label"] = VERIFICATION_STATUSES["pending"]
    else:
        raise ValueError(f"Unknown review action '{kind}'. Use confirm, reject, edit or reset.")

    if note:
        updated["reviewer_note"] = note
    return updated


def new_finding(payload: dict) -> dict:
    """Create a reviewer-authored finding (the 'Add finding' control)."""
    statement = str(payload.get("statement", "")).strip()
    if not statement:
        raise ValueError("A new finding needs at least a statement.")
    category = str(payload.get("category", "uncertain")).strip().lower()
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}'.")
    finding = _finding(
        f"manual-{abs(hash(statement)) % 100000:05d}",
        category,
        statement,
        str(payload.get("visible", "")).strip() or "Added manually by the reviewer.",
        str(payload.get("why", "")).strip() or "Added manually by the reviewer.",
        str(payload.get("suggested_correction", "")).strip(),
        "added manually by the reviewer",
        "high",
    )
    finding["verification_status"] = "edited"
    finding["verification_label"] = VERIFICATION_STATUSES["edited"]
    finding["reviewer_note"] = str(payload.get("note", "")).strip()
    return finding


# --------------------------------------------------------- review storage ----
class ReviewStore:
    """Tiny JSON-file store for reviewer decisions, keyed by analysis id.

    Uploaded images are never written to disk, but reviewer decisions are small
    pieces of text, and keeping them makes the evaluation screen useful across
    restarts. The file lives under ``instance/`` and is git-ignored.
    """

    def __init__(self, path):
        self.path = path
        self._cache: dict[str, list[dict]] | None = None

    def _load(self) -> dict[str, list[dict]]:
        if self._cache is not None:
            return self._cache
        import json
        from pathlib import Path

        file_path = Path(self.path)
        if file_path.exists():
            try:
                self._cache = json.loads(file_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._cache = {}
        else:
            self._cache = {}
        return self._cache

    def _save(self) -> None:
        import json
        from pathlib import Path

        file_path = Path(self.path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(self._load(), indent=2), encoding="utf-8")

    def actions_for(self, analysis_id: str) -> list[dict]:
        return list(self._load().get(analysis_id, []))

    def add_action(self, analysis_id: str, action: dict) -> list[dict]:
        data = self._load()
        actions = data.setdefault(analysis_id, [])
        if action.get("type") == "add":
            actions.append({"type": "add", "finding": action.get("finding", {})})
        else:
            actions.append(action)
        self._save()
        return list(actions)

    def clear(self, analysis_id: str) -> None:
        data = self._load()
        data.pop(analysis_id, None)
        self._save()


def apply_actions(findings: list[dict], actions: list[dict]) -> list[dict]:
    """Replay stored reviewer actions over freshly computed findings."""
    current = [dict(f) for f in findings]
    index = {f["id"]: i for i, f in enumerate(current)}
    for action in actions:
        kind = str(action.get("type", "")).lower()
        if kind == "add":
            try:
                current.append(new_finding(action.get("finding", {})))
                index[current[-1]["id"]] = len(current) - 1
            except ValueError:
                continue
            continue
        position = index.get(action.get("finding_id"))
        if position is None:
            continue
        try:
            current[position] = apply_review(current[position], action)
        except ValueError:
            continue
    return current


SECOND_OPINION_LABEL = (
    "Second-opinion review: this assessment was produced by another AI model. It is not independent "
    "ground truth and it can be wrong in the same way as the analysis it reviews; a human must still "
    "verify every point."
)
