"""Q1: Prompt-based information extraction (unstructured text -> validated JSON)."""
import json, os, re
from anthropic import Anthropic

MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
FIELDS = ["title", "date", "venue", "speaker", "topics"]

# (b) Structured prompt: role + task + schema + output rules
PROMPT_V1 = """You are an information extraction system.
Extract details of the technical workshop from the paragraph.
Return ONLY a JSON object with exactly these fields:
{{"title": string, "date": string, "venue": string, "speaker": string, "topics": [string]}}
No explanations, no markdown.

Paragraph:
\"\"\"{text}\"\"\""""

# (d) Improved prompt: explicit missing-information handling, no invention
PROMPT_V2 = """You are an information extraction system.
Extract details of the technical workshop from the paragraph.
Return ONLY a JSON object with exactly these fields:
{{"title": string|null, "date": string|null, "venue": string|null, "speaker": string|null, "topics": [string]}}

Rules:
1. Use ONLY information explicitly stated in the paragraph.
2. If a field is not stated, use null (or [] for topics). NEVER guess, infer or invent values.
3. Keep wording close to the text; date as written in the paragraph.
4. Output must be valid JSON. No explanations, no markdown.

Paragraph:
\"\"\"{text}\"\"\""""

# (a) + (e) three test paragraphs (the 3rd deliberately has missing info)
PARAGRAPHS = {
    "P1_complete": "The Department of Computer Engineering will host a one-day workshop titled 'Hands-On Generative AI' on 14 November 2026 at the Seminar Hall, Block B, Pune. The session will be led by Dr. Anita Deshmukh, who will cover prompt engineering, structured outputs, and building simple RAG pipelines.",
    "P2_different_style": "Join us at Innovation Lab 3 on 2 December 2026 for 'Cloud Security Bootcamp'. Speaker Rahul Mehta from SecureNet will walk through IAM best practices, container security and incident response basics.",
    "P3_missing_info": "A workshop on Edge AI for IoT devices is being organised next month. Participants will learn about model quantisation and deploying TinyML models on microcontrollers. The speaker will be announced soon.",
}

def validate(obj, source_text, allow_null):
    """(e) Structural validation + simple grounding check against the source text."""
    errors = []
    if not isinstance(obj, dict): return ["Not a JSON object"]
    if set(obj) != set(FIELDS):
        errors.append(f"Field mismatch: got {sorted(obj)}")
    for f in ["title", "date", "venue", "speaker"]:
        v = obj.get(f)
        if v is None:
            if not allow_null: errors.append(f"{f} is null")
        elif not isinstance(v, str): errors.append(f"{f} not a string")
        elif f != "date" and v.lower() not in source_text.lower():
            errors.append(f"{f}='{v}' not found in source (possible invention)")
    t = obj.get("topics")
    if not isinstance(t, list) or not all(isinstance(x, str) for x in t):
        errors.append("topics must be a list of strings")
    return errors

def call(client, prompt):
    r = client.messages.create(
    model=MODEL,
    max_tokens=500,
    messages=[
        {"role": "user", "content": prompt}
    ]
)
    return r.content[0].text.strip()

def parse(raw):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    return json.loads(raw)

if __name__ == "__main__":
    client = Anthropic()  # reads ANTHROPIC_API_KEY
    results, rows = [], ["| Paragraph | Prompt | Valid JSON | Schema/grounding errors |", "|---|---|---|---|"]
    for name, text in PARAGRAPHS.items():
        for label, tpl, allow_null in [("v1", PROMPT_V1, False), ("v2", PROMPT_V2, True)]:
            raw = call(client, tpl.format(text=text))
            try:
                obj = parse(raw); valid = True; errs = validate(obj, text, allow_null)
            except json.JSONDecodeError as e:
                obj, valid, errs = None, False, [f"JSON error: {e}"]
            results.append({"paragraph": name, "prompt": label, "raw": raw, "parsed": obj, "valid_json": valid, "errors": errs})
            rows.append(f"| {name} | {label} | {'Yes' if valid else 'No'} | {'; '.join(errs) or 'None'} |")
            print(f"\n[{name} / {label}]\n{raw}\nErrors: {errs or 'none'}")
    json.dump(results, open("results.json", "w"), indent=2)
    open("validation_report.md", "w").write("# Validation Results\n\n" + "\n".join(rows) + "\n")
    print("\nSaved results.json and validation_report.md")
