"""Offline demonstration data for the three required image examples.

HONESTY CONTRACT (please read before the viva)
----------------------------------------------
* The three images in ``images/`` are **original drawings** produced by
  ``make_sample_images.py`` with Pillow. They are not photographs and they are
  not copied from the internet, so no third-party licence is involved and the
  exact contents of every picture are known.
* The six-field analyses below are **hand-written illustrative sample data**.
  They were NOT produced by a live vision-language model. The UI, the API and
  the report all say so, and ``api/analyze`` refuses to attach them to any
  image whose SHA-256 digest does not match the sample file exactly.
* The analyses intentionally reproduce the *kind* of weaknesses that real
  vision-language models show (an interpretation presented as an observation,
  invented readable text, an activity with no visible agent, missing objects).
  The evaluation module then detects those weaknesses in the text. This is
  stated openly in docs/EVALUATION_RESULTS.md: the findings are real properties
  of this sample text, not invented results.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

IMAGES_DIR = Path(__file__).parent / "images"

OFFLINE_BANNER = (
    "Offline Demo Mode — Results are illustrative sample data, "
    "not AI-generated analysis of the uploaded image."
)

SAMPLE_DATA_NOTICE = (
    "Illustrative sample data: this text was written by hand for the offline demonstration. "
    "It is not the output of a live vision-language model."
)

ILLUSTRATIVE_EVALUATION_NOTICE = (
    "Illustrative example: these findings come from comparing the hand-written sample analysis with the "
    "actual sample image. In Live AI mode the identical checks are applied to real model output."
)

OFFLINE_UNSUPPORTED_MESSAGE = (
    "Offline Demo Mode can only explain the three bundled example images, because no vision-language "
    "model is configured. Live model access (an API key) is required to analyse this image for real. "
    "Your image was validated and previewed successfully, but no sample description has been applied to it."
)


def _sha256(name: str) -> str:
    path = IMAGES_DIR / name
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


SAMPLES: dict[str, dict] = {
    # ------------------------------------------------------------------ 1 ---
    "education": {
        "key": "education",
        "title": "Image 1 — Education: student studying",
        "category": "Education",
        "filename": "education.jpg",
        "url": "/images/education.jpg",
        "source": "Original artwork generated for this project by make_sample_images.py (Pillow).",
        "licence": "Original work by the student, released for this practical examination (no third-party rights).",
        "illustrative": True,
        "ground_truth": [
            "A seated human figure (round head, brown hair, blue sweater) is drawn behind a wooden desk.",
            "An open laptop sits on the desk in front of the figure; its screen shows only grey lines, no readable text.",
            "An open spiral-bound notebook with ruled lines lies on the desk, with a dark pen lying diagonally across it.",
            "A stack of three closed books (red, green, yellow) sits to the right of the notebook.",
            "A white mug with a handle stands on the desk; three white steam arcs rise above it.",
            "A desk lamp with a yellow shade and grey stand stands at the left of the desk.",
            "A window with white mullions and a yellow sun is drawn on the upper-left wall.",
            "A blank notice board with four grey rule lines hangs on the upper-right wall.",
            "No legible text, logo, brand or location is visible anywhere in the picture.",
            "The figure has no drawn facial features, so no expression or emotion can be observed.",
        ],
        "analysis": {
            "detailed_description": (
                "A person in a blue sweater sits at a wooden desk with an open laptop in front of them. "
                "The laptop screen shows several grey lines of content but no readable text. "
                "To the left of the laptop is an open spiral notebook with ruled pages and a dark pen lying "
                "across it. A stack of three closed books - red, green and yellow - rests on the right side "
                "of the desk next to a white mug. The person appears to be concentrating on the laptop screen."
            ),
            "objects": [
                {
                    "name": "Person",
                    "attributes": ["seated", "blue sweater", "brown hair"],
                    "evidence": "A human figure is drawn behind the desk at the centre of the image.",
                },
                {
                    "name": "Laptop",
                    "attributes": ["open", "grey screen lines", "on desk"],
                    "evidence": "An open laptop occupies the centre-left area of the desk.",
                },
                {
                    "name": "Notebook",
                    "attributes": ["open", "spiral bound", "ruled pages"],
                    "evidence": "An open notebook with a visible spiral binding lies on the desk.",
                },
                {
                    "name": "Pen",
                    "attributes": ["dark", "lying diagonally"],
                    "evidence": "A dark pen is drawn diagonally across the notebook.",
                },
                {
                    "name": "Books",
                    "attributes": ["three", "red", "green", "yellow", "stacked"],
                    "evidence": "Three coloured book shapes are stacked at the right of the desk.",
                },
                {
                    "name": "Mug",
                    "attributes": ["white", "handle", "steam above"],
                    "evidence": "A white mug with a handle stands on the desk right of the books.",
                },
            ],
            "activities": ["sitting at a desk", "working on a laptop"],
            "caption": "A student works on a laptop at a desk surrounded by books and notes.",
            "summary": (
                "The image shows a study scene: a seated person working at an open laptop on a wooden desk, "
                "with an open notebook, a pen, a stack of books and a mug around them."
            ),
            "uncertainties": [],
        },
        "curated_findings": [
            {
                "id": "edu-f1",
                "category": "unsupported",
                "statement": "The person appears to be concentrating on the laptop screen.",
                "visible": "The figure has no drawn facial features and no eye direction; the picture shows a seated person next to an open laptop and nothing about attention.",
                "why": "Concentration is an internal mental state. It cannot be observed from pixels, so the sentence is an interpretation presented as an observation - the classic 'unsupported claim' failure.",
                "suggested_correction": "A person is seated at a desk facing an open laptop. (Keep the mental state out, or move it to \"uncertainties\" as an interpretation.)",
            },
            {
                "id": "edu-f2",
                "category": "omission",
                "statement": "(no statement - the description never mentions the desk lamp or the window)",
                "visible": "A grey desk lamp with a yellow shade stands at the left of the desk, and a white-mullioned window with a yellow sun is drawn on the upper-left wall.",
                "why": "Both objects occupy a large part of the frame and are clearly visible, so leaving them out loses real information. In Live AI mode this class of gap is found by comparing the description with a human ground-truth list.",
                "suggested_correction": "Add: 'A desk lamp with a yellow shade stands at the left of the desk, and a window with white mullions and a sun is visible on the wall behind.'",
            },
            {
                "id": "edu-f3",
                "category": "uncertain",
                "statement": "The hedged phrase 'appears to be' is used while \"uncertainties\" is returned as an empty array.",
                "visible": "The analysis text itself is the evidence: it hedges in one field and reports no uncertainty in another.",
                "why": "The prompt requires every hedged statement to be repeated in \"uncertainties\". Leaving that array empty hides the model's own doubt from the reader.",
                "suggested_correction": "Either write the fact plainly, or list 'what the person is doing is inferred from posture only' in \"uncertainties\".",
            },
        ],
    },
    # ------------------------------------------------------------------ 2 ---
    "technology": {
        "key": "technology",
        "title": "Image 2 — Technology: computer workspace",
        "category": "Technology",
        "filename": "technology.jpg",
        "url": "/images/technology.jpg",
        "source": "Original artwork generated for this project by make_sample_images.py (Pillow).",
        "licence": "Original work by the student, released for this practical examination (no third-party rights).",
        "illustrative": True,
        "ground_truth": [
            "A large grey monitor stands on a grey desk; its screen shows seven blue bars of different heights and a red line graph above them.",
            "No text, axis labels or numbers are drawn anywhere on the screen - the bars have no readable labels.",
            "An open laptop sits at the right of the desk; its screen shows an empty panel and two grey bars, again with no readable text.",
            "A light keyboard with four rows of keys lies at the front-left of the desk; a mouse is drawn next to it.",
            "A white mug stands between the mouse and the laptop.",
            "A potted plant with green leaves and a terracotta pot stands at the right edge, partly in front of the laptop.",
            "A smartphone with a blue screen and a 3x3 grid of pale tiles stands at the left edge of the desk.",
            "A grey cable runs from the monitor base towards the keyboard.",
            "No person, no chair and no hands are visible anywhere in the image.",
        ],
        "analysis": {
            "detailed_description": (
                "A computer workstation is set up on a grey desk. A large monitor in the centre displays a chart of "
                "seven blue bars and a red line graph. To its right an open laptop shows a mostly empty screen with "
                "two grey panels. A light grey keyboard and a mouse lie at the front of the desk, and a white mug "
                "stands between them and the laptop. The monitor is showing a summary report of the data that is "
                "being analysed."
            ),
            "objects": [
                {
                    "name": "Monitor",
                    "attributes": ["grey", "centre of desk", "shows bar chart and line graph"],
                    "evidence": "A large grey monitor is in the centre of the image with bars and a red line on its screen.",
                },
                {
                    "name": "Laptop",
                    "attributes": ["open", "right side", "pale screen"],
                    "evidence": "An open laptop is drawn at the right of the desk next to the monitor.",
                },
                {
                    "name": "Keyboard",
                    "attributes": ["light grey", "four key rows"],
                    "evidence": "A keyboard with visible key rows lies at the front-left of the desk.",
                },
                {
                    "name": "Mouse",
                    "attributes": ["white", "next to the keyboard"],
                    "evidence": "A rounded white mouse is drawn to the right of the keyboard.",
                },
                {
                    "name": "Mug",
                    "attributes": ["white", "handle"],
                    "evidence": "A white mug with a handle stands between the mouse and the laptop.",
                },
            ],
            "activities": ["analysing chart data on a monitor"],
            "caption": "A desktop workstation with a monitor showing a bar chart and a line graph.",
            "summary": (
                "The image shows a computer workspace: a monitor displaying a chart, an open laptop, a keyboard, "
                "a mouse and a mug on a grey desk."
            ),
            "uncertainties": [],
        },
        "curated_findings": [
            {
                "id": "tech-f1",
                "category": "unsupported",
                "statement": "The monitor is showing a summary report of the data that is being analysed.",
                "visible": "The monitor shows seven blue bars and a red line graph. No words, numbers or axis labels are drawn on the screen.",
                "why": "Calling it a 'summary report' invents a document type, and inventing readable content is exactly what the base prompt forbids. The chart shape is visible; the meaning of the chart is not.",
                "suggested_correction": "'The monitor displays a bar chart with seven bars and a red line graph.' Do not name the document or imply readable labels.",
            },
            {
                "id": "tech-f2",
                "category": "unsupported",
                "statement": "analysing chart data on a monitor (listed as an activity)",
                "visible": "No person, hands, chair or any other agent appears anywhere in the image.",
                "why": "An activity needs an actor. With no person visible, the activity is an inference about who might use the workstation, not something the image shows.",
                "suggested_correction": "Set \"activities\": [] and mention in \"uncertainties\" that the equipment is arranged as if for active use.",
            },
            {
                "id": "tech-f3",
                "category": "omission",
                "statement": "(no statement - the description never mentions the potted plant, the smartphone or the cable)",
                "visible": "A green potted plant stands at the right edge, a smartphone with a blue screen sits at the left edge, and a grey cable runs from the monitor base.",
                "why": "Three clearly visible objects are missing from the description, so the description under-reports the scene even though the text itself is well formed.",
                "suggested_correction": "Add the plant, the smartphone and the cable to the description and to the \"objects\" array (with evidence for each).",
            },
        ],
    },
    # ------------------------------------------------------------------ 3 ---
    "everyday_objects": {
        "key": "everyday_objects",
        "title": "Image 3 — Everyday objects on a table",
        "category": "Everyday objects",
        "filename": "everyday_objects.jpg",
        "url": "/images/everyday_objects.jpg",
        "source": "Original artwork generated for this project by make_sample_images.py (Pillow).",
        "licence": "Original work by the student, released for this practical examination (no third-party rights).",
        "illustrative": True,
        "ground_truth": [
            "A light-blue water bottle with a dark blue cap and a plain white label band stands at the left.",
            "The bottle is closed: the cap is present on the neck.",
            "A closed red notebook with a dark spine, an elastic band and a blank white label lies in the centre.",
            "A black pen with a grey grip and a silver clip lies diagonally across the notebook.",
            "A smartphone with a blue screen and a 3x3 grid of pale tiles stands upright to the right of the notebook.",
            "A pair of spectacles with blue-grey frames lies to the right of the smartphone.",
            "The objects rest on a beige table; the wall behind is light grey-blue.",
            "No legible text is drawn on the notebook label, the bottle label or the smartphone screen.",
        ],
        "analysis": {
            "detailed_description": (
                "Several everyday objects are arranged on a beige table. On the left stands a light-blue water "
                "bottle with a dark blue cap and a white label. In the centre is a closed red notebook with a dark "
                "spine, and a black pen lies diagonally across it. The notebook has a label on the front with a "
                "product name printed on it. To the right of the notebook a smartphone stands upright, showing a "
                "grid of application tiles on its blue screen."
            ),
            "objects": [
                {
                    "name": "Water bottle",
                    "attributes": ["light blue", "dark blue cap", "white label"],
                    "evidence": "A tall light-blue bottle with a dark cap and a white band is drawn at the left of the table.",
                },
                {
                    "name": "Notebook",
                    "attributes": ["closed", "red cover", "dark spine"],
                    "evidence": "A closed red notebook with a dark spine lies in the centre of the table.",
                },
                {
                    "name": "Pen",
                    "attributes": ["black", "grey grip"],
                    "evidence": "A black pen with a grey grip lies diagonally across the notebook.",
                },
                {
                    "name": "Smartphone",
                    "attributes": ["upright", "blue screen", "grid of tiles"],
                    "evidence": "A smartphone is drawn standing upright to the right of the notebook with tiles on its screen.",
                },
            ],
            "activities": [],
            "caption": "Everyday desk objects arranged on a table: a bottle, a notebook, a pen and a phone.",
            "summary": (
                "A still-life arrangement of everyday objects on a table: a water bottle, a closed red notebook "
                "with a pen across it, and a smartphone."
            ),
            "uncertainties": [],
        },
        "curated_findings": [
            {
                "id": "obj-f1",
                "category": "unsupported",
                "statement": "The notebook has a label on the front with a product name printed on it.",
                "visible": "The notebook does have a white label rectangle, but it is blank - no letters or digits are drawn on it.",
                "why": "This is invented readable text: the model-style text converts 'there is a label' into 'the label has a product name'. It is the single most common hallucination on still-life images and cannot be verified from the pixels.",
                "suggested_correction": "'The notebook has a blank white label area on its front cover.' Never claim text content that is not legible.",
            },
            {
                "id": "obj-f2",
                "category": "omission",
                "statement": "(no statement - the description never mentions the spectacles)",
                "visible": "A pair of blue-grey framed spectacles lies clearly to the right of the smartphone.",
                "why": "The glasses are a distinct object in the right part of the frame and are absent from both the description and the \"objects\" array.",
                "suggested_correction": "Add: 'A pair of spectacles with blue-grey frames lies to the right of the smartphone.'",
            },
            {
                "id": "obj-f3",
                "category": "uncertain",
                "statement": "The smartphone shows a grid of application tiles on its blue screen.",
                "visible": "The phone screen shows nine identical pale squares in a 3x3 layout on a blue background. Nothing identifies them as applications.",
                "why": "Naming the squares 'application tiles' assigns a function that the image does not establish - the shapes could be any kind of menu or blocks. This is a mild interpretation, so it is classified as an uncertain detail rather than a clear error.",
                "suggested_correction": "'The phone screen shows a 3x3 grid of pale square shapes on a blue background.'",
            },
        ],
    },
}

SAMPLE_ORDER: tuple[str, ...] = ("education", "technology", "everyday_objects")


def get_sample(key: str) -> dict | None:
    return SAMPLES.get((key or "").strip().lower())


def match_by_digest(digest: str) -> dict | None:
    """Return the sample whose file hash equals ``digest`` (exact-match rule).

    Offline mode may only reuse a sample analysis when the uploaded bytes are
    *identical* to the sample file. Anything else would be misrepresenting the
    uploaded image, which the assignment forbids.
    """
    if not digest:
        return None
    for key in SAMPLE_ORDER:
        if SAMPLES[key]["digest"] == digest:
            return SAMPLES[key]
    return None


def metadata() -> list[dict]:
    """Public sample metadata for GET /api/samples (no analysis text)."""
    out = []
    for key in SAMPLE_ORDER:
        sample = SAMPLES[key]
        out.append(
            {
                "key": key,
                "title": sample["title"],
                "category": sample["category"],
                "filename": sample["filename"],
                "url": sample["url"],
                "digest": sample["digest"],
                "source": sample["source"],
                "licence": sample["licence"],
                "illustrative": True,
                "ground_truth_count": len(sample["ground_truth"]),
            }
        )
    return out


def image_info(name: str) -> dict:
    """Dimensions / size / digest of a sample file, without loading Pillow."""
    from PIL import Image

    path = IMAGES_DIR / name
    with Image.open(path) as img:
        width, height = img.size
        fmt = img.format
    return {
        "filename": name,
        "width": width,
        "height": height,
        "format": fmt,
        "bytes": path.stat().st_size,
        "digest": _sha256(name),
    }


# fill in the digests at import time (empty string when an image is missing)
for _key in SAMPLE_ORDER:
    SAMPLES[_key]["digest"] = _sha256(SAMPLES[_key]["filename"])
