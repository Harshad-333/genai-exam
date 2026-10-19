"""Downloadable report generation (Markdown and JSON).

The report is built from the *actual* payload returned by /api/analyze and
/api/evaluate, so a demonstration report can never invent a result: whatever the
user sees on screen is what lands in the file.
"""

from __future__ import annotations

import datetime as dt
import json

from evaluator import CATEGORIES, VERIFICATION_STATUSES
from prompts import BASE_PROMPT, FIELD_RULES, STRUCTURED_PROMPT

STUDENT = {
    "name": "Harshad Babulal Imale",
    "course": "MCA (Master of Computer Applications)",
    "college": "DKTE Society's Textile & Engineering Institute, Ichalkaranji",
    "subject": "Generative AI Practical — Q.3 Multimodal Generative AI Application",
    "marks": "25 Marks",
}


def _flag(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def build_markdown(payload: dict) -> str:
    image = payload.get("image") or {}
    meta = payload.get("meta") or {}
    analysis = payload.get("analysis") or {}
    validation = payload.get("validation") or {}
    evaluation = payload.get("evaluation") or {}
    findings = evaluation.get("findings") or []
    generated = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    lines: list[str] = []
    add = lines.append

    add("# Multimodal AI-Based Image Understanding System — Evaluation Report")
    add("")
    add(f"| Field | Value |")
    add("|---|---|")
    add(f"| Student | {STUDENT['name']} |")
    add(f"| Course | {STUDENT['course']} |")
    add(f"| College | {STUDENT['college']} |")
    add(f"| Question | {STUDENT['subject']} ({STUDENT['marks']}) |")
    add(f"| Report generated | {generated} |")
    add("")

    add("## 1. Execution mode (honesty statement)")
    add("")
    add(f"- **Mode:** {meta.get('mode_label', meta.get('mode', 'unknown'))}")
    add(f"- **Provider:** {meta.get('provider') or 'n/a'}")
    add(f"- **Model:** {meta.get('model') or 'n/a'}")
    add(f"- **Latency:** {meta.get('latency_ms', 'n/a')} ms")
    add(f"- **Request started / finished:** {meta.get('started_at', '?')} / {meta.get('finished_at', '?')}")
    add(f"- **Illustrative sample data:** {_flag(meta.get('illustrative'))}")
    if meta.get("banner"):
        add("")
        add(f"> **{meta['banner']}**")
    notes = meta.get("notes") or []
    if notes:
        add("")
        add("Notes recorded by the application:")
        add("")
        for note in notes:
            add(f"- {note}")
    add("")

    add("## 2. Image under analysis")
    add("")
    add(f"- File name: `{image.get('filename', 'n/a')}`")
    add(f"- Dimensions: {image.get('width', '?')} x {image.get('height', '?')} px")
    add(f"- Size: {round((image.get('bytes') or 0) / 1024, 1)} KB")
    add(f"- Validated media type: {image.get('media_type', 'n/a')}")
    add(f"- SHA-256: `{image.get('digest', 'n/a')}`")
    add("- Storage: the uploaded file was processed in memory and was not written to disk.")
    add("")

    add("## 3. Generated analysis")
    add("")
    add("**Detailed description**")
    add("")
    add(f"> {analysis.get('detailed_description', 'n/a')}")
    add("")
    add("**Objects and visible attributes**")
    add("")
    add("| Object | Attributes | Evidence in the image |")
    add("|---|---|---|")
    for obj in analysis.get("objects") or []:
        attrs = ", ".join(obj.get("attributes") or []) or "—"
        add(f"| {obj.get('name', '')} | {attrs} | {obj.get('evidence', '')} |")
    if not (analysis.get("objects") or []):
        add("| — | — | no objects reported |")
    add("")
    activities = analysis.get("activities") or []
    add(f"**Activities:** {', '.join(activities) if activities else 'none reported'}")
    add("")
    add(f"**Caption:** {analysis.get('caption', 'n/a')}")
    add("")
    add(f"**Summary:** {analysis.get('summary', 'n/a')}")
    add("")
    uncertainties = analysis.get("uncertainties") or []
    add(f"**Uncertainties reported by the model/analysis:** {', '.join(uncertainties) if uncertainties else 'none'}")
    add("")

    add("## 4. JSON schema validation")
    add("")
    add(f"- Status: **{validation.get('status', 'unknown')}**")
    add(f"- Errors: {validation.get('error_count', 0)}")
    add(f"- Warnings: {validation.get('warning_count', 0)}")
    for warning in validation.get("warnings") or []:
        add(f"  - ⚠ {warning}")
    for error in validation.get("errors") or []:
        add(f"  - ✖ {error.get('field')}: {error.get('message')}")
    add("")
    add("> Passing schema validation proves the JSON is well formed and complete. It does not prove that the "
        "content is factually correct, because a model can describe an object that is not in the picture while "
        "producing perfectly valid JSON.")
    add("")

    add("## 5. Evaluation of errors, omissions and unsupported observations")
    add("")
    if evaluation.get("illustrative"):
        add("> Illustrative example: the findings below come from comparing hand-written sample analysis text with "
            "the actual sample image. In Live AI mode the same automatic checks run on real model output.")
        add("")
    add(f"Findings raised: **{evaluation.get('total', 0)}** — " + ", ".join(
        f"{CATEGORIES[k]}: {evaluation.get('counts', {}).get(k, 0)}" for k in CATEGORIES))
    add("")
    add("| # | Category | Generated statement | What is actually visible | Why it is a problem | Suggested correction | Review status |")
    add("|---|---|---|---|---|---|---|")
    for i, finding in enumerate(findings, start=1):
        status = VERIFICATION_STATUSES.get(finding.get("verification_status", "pending"), finding.get("verification_status", ""))
        if finding.get("reviewer_note"):
            status += f" (note: {finding['reviewer_note']})"
        add("| {} | {} | {} | {} | {} | {} | {} |".format(
            i,
            finding.get("category_label", finding.get("category", "")),
            _cell(finding.get("statement", "")),
            _cell(finding.get("visible", "")),
            _cell(finding.get("why", "")),
            _cell(finding.get("suggested_correction", "")),
            status,
        ))
    if not findings:
        add("| — | — | — | — | — | — | — |")
    add("")
    add(f"> {evaluation.get('disclaimer', '')}")
    add("")
    add(f"> How these findings were produced: {evaluation.get('how_produced', '')}")
    add("")

    ground_truth = evaluation.get("ground_truth") or []
    if ground_truth:
        add("## 6. Human ground-truth checklist used for this image")
        add("")
        for item in ground_truth:
            add(f"- {item}")
        add("")
        add("The checklist documents what a human observer verifies directly in the picture; the automatic checks "
            "cannot do this, which is exactly why the evaluation stage is needed.")
        add("")

    second = payload.get("second_opinion")
    if second:
        add("## 7. Second-opinion AI review (optional feature)")
        add("")
        add(f"- Reviewer provider/model: {second.get('provider')} / {second.get('model')}")
        add(f"- {second.get('label', '')}")
        for item in second.get("concerns") or []:
            add(f"- **{item.get('statement')}** ({item.get('category')}) — {item.get('explanation')} "
                f"Suggested correction: {item.get('suggested_correction')}")
        add("")

    add("## 8. Prompt used for the analysis")
    add("")
    add("```text")
    add(STRUCTURED_PROMPT)
    add("```")
    add("")
    add("Base prompt required by the assignment:")
    add("")
    add("```text")
    add(BASE_PROMPT)
    add("```")
    add("")

    add("## 9. Limitations of this report")
    add("")
    add("- A single image and a single model: results do not generalise to other pictures or other models.")
    add("- Automatic checks are text-level heuristics; they cannot see the image, so they raise hypotheses, not proofs.")
    add("- The sample analyses in Offline Demo Mode were written by hand and are labelled as illustrative.")
    add("- Confidence values are qualitative labels, not calibrated probabilities.")
    add("- Human review is required before any finding is treated as a result.")
    add("")
    add("---")
    add("")
    add("Generated by the Multimodal AI-Based Image Understanding System "
        "(Flask + Python). Offline demo data and live AI output are always labelled separately.")
    add("")
    return "\n".join(lines)


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def build_json(payload: dict) -> str:
    document = {
        "report_type": "multimodal_image_understanding_evaluation",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "student": STUDENT,
        "image": payload.get("image"),
        "execution": payload.get("meta"),
        "analysis": payload.get("analysis"),
        "schema_validation": payload.get("validation"),
        "evaluation": payload.get("evaluation"),
        "second_opinion": payload.get("second_opinion"),
        "prompt": {
            "base_prompt": BASE_PROMPT,
            "field_rules": FIELD_RULES,
            "structured_prompt": STRUCTURED_PROMPT,
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False)
