"""Q3: Multimodal image understanding with a vision-language model."""
import base64, json, os, re, glob
from anthropic import Anthropic

MODEL = os.getenv("MODEL", "claude-sonnet-5-5")
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}

PROMPT = """Analyse this image. Describe only what is visibly present; do not guess unseen details.
Return ONLY valid JSON:
{"description": "3-4 sentence detailed description",
 "objects": ["..."], "activities": ["..."], "visual_elements": ["colours, setting, text, lighting"],
 "caption": "one catchy line under 12 words",
 "summary": "2 sentence summary"}"""

client = Anthropic()
results = {}
for path in sorted(glob.glob("images/*")):
    ext = os.path.splitext(path)[1].lower()
    if ext not in MEDIA: continue
    data = base64.standard_b64encode(open(path, "rb").read()).decode()
    r = client.messages.create(model=MODEL, max_tokens=800, messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": MEDIA[ext], "data": data}},
        {"type": "text", "text": PROMPT}]}])
    raw = re.sub(r"^```(?:json)?|```$", "", r.content[0].text.strip(), flags=re.M).strip()
    results[os.path.basename(path)] = json.loads(raw)
    print(f"\n== {path} ==\n{json.dumps(results[os.path.basename(path)], indent=2)}")

json.dump(results, open("results.json", "w"), indent=2)
with open("outputs.md", "w") as f:
    f.write("# Generated Outputs\n")
    for name, d in results.items():
        f.write(f"\n## {name}\n![{name}](images/{name})\n\n**Caption:** {d['caption']}\n\n**Summary:** {d['summary']}\n\n"
                f"**Description:** {d['description']}\n\n**Objects:** {', '.join(d['objects'])}\n\n"
                f"**Activities:** {', '.join(d['activities'])}\n\n**Visual elements:** {', '.join(d['visual_elements'])}\n")
print("\nSaved results.json and outputs.md")
