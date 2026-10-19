# Generative AI Practical Exam

| Question | Folder | Marks |
|---|---|---|
| Q1 Prompt Engineering & Structured Output | `q1_extraction/` | 25 |
| Q3 Multimodal Image Understanding | `q3_multimodal/` | 25 |

## Setup
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key      # Windows: set ANTHROPIC_API_KEY=your_key
```

## Q1 – Information Extraction
```bash
cd q1_extraction && python extract.py
```
- Prompt v1 = basic structured prompt; v2 = handles missing info with `null` / `[]`, no invention.
- Tests 3 paragraphs (the 3rd has missing info). Validation checks: valid JSON, exact field names, types, and that values appear in the source text.
- Output: `results.json`, `validation_report.md`.

## Q3 – Multimodal Image Understanding
1. Put 3 images (education / technology / everyday objects) in `q3_multimodal/images/`.
2. `cd q3_multimodal && python describe.py`
3. Output: `results.json`, `outputs.md` (description, objects, activities, caption, summary).
4. Fill in `evaluation_report.md` with at least two real errors/omissions/unsupported claims.
