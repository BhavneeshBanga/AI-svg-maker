from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from datetime import datetime
import requests
import re
import os

load_dotenv()

app = Flask(__name__)

# ── Sarvam API config ─────────────────────────────────────────────────
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_API_URL = "https://api.sarvam.ai/v1/chat/completions"
MODEL          = "sarvam-m"

# ── Logging folder — all SVGs saved here forever ─────────────────────
LOG_DIR = "svg_logs"
os.makedirs(LOG_DIR, exist_ok=True)

if not SARVAM_API_KEY:
    raise EnvironmentError(
        "\n\n  SARVAM_API_KEY not found!"
        "\n  Add this to your .env file:"
        "\n  SARVAM_API_KEY=your_actual_key_here\n"
    )

# ── System prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an SVG flowchart generator. You only output raw SVG code. No explanation. No prose. No markdown. No backticks. Your entire response must be one valid SVG element — starting with <svg and ending with </svg>.

═══════════════════════════════════════
CANVAS
═══════════════════════════════════════
Always use:
  <svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 680 H">

viewBox width is ALWAYS 680. Never change it.

Set H = (number of rows × 100) + 100. Count rows first, then set H.
  4 or fewer rows  → H = 500
  5–7 rows         → H = 700
  8–11 rows        → H = 950
  12+ rows         → H = 1250

Safe drawing zone: x = 40 to 640, y = 40 to (H - 40).

═══════════════════════════════════════
ALWAYS START WITH THIS EXACT <defs>
═══════════════════════════════════════
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>

NOTE: stroke="context-stroke" — NOT "#666". This makes arrow heads inherit the line color.

═══════════════════════════════════════
BOX (process node)
═══════════════════════════════════════
Standard size: width=200 height=56 rx=8
Main column center: x=340 → rect x=240

Title  y = box_y + 20   dominant-baseline="central"   font-size="14" font-weight="500"
Sub    y = box_y + 38   dominant-baseline="central"   font-size="12" font-weight="400"
Both:  text-anchor="middle"   x = box_x + 100

CORRECT box at y=40:
<rect x="240" y="40" width="200" height="56" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="340" y="60"  font-family="sans-serif" font-size="14" font-weight="500" fill="#0C447C" text-anchor="middle" dominant-baseline="central">Box title</text>
<text x="340" y="78"  font-family="sans-serif" font-size="12" font-weight="400" fill="#185FA5" text-anchor="middle" dominant-baseline="central">short subtitle</text>

WRONG — never put two texts at the same y:
<text y="70">Title</text>
<text y="70">Subtitle</text>   ← OVERLAP, WRONG

═══════════════════════════════════════
DIAMOND (decision node)
═══════════════════════════════════════
Center at (cx, cy). Half-width=90, half-height=40.
Points: TOP=(cx, cy-40)  RIGHT=(cx+90, cy)  BOTTOM=(cx, cy+40)  LEFT=(cx-90, cy)

CORRECT — center at (340, 200):
<polygon points="340,160 430,200 340,240 250,200" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="340" y="196" font-family="sans-serif" font-size="13" font-weight="500" fill="#633806" text-anchor="middle" dominant-baseline="central">Question label?</text>

WRONG — never set TOP and RIGHT at the same y (creates a flat line, not a diamond):
<polygon points="340,200 430,200 ..."/>   ← WRONG

═══════════════════════════════════════
LAYOUT GRID
═══════════════════════════════════════
Main column center: x = 340   (rect x=240, polygon cx=340)
Left branch:        x = 130   (rect x=30,  polygon cx=130)
Right branch:       x = 570   (rect x=470, polygon cx=570)

Vertical step = 110px per row (56px box + 54px gap).
Row 1: y=30   Row 2: y=140   Row 3: y=250   Row 4: y=360 ... etc.

Minimum gap between any two boxes: 40px vertically, 20px horizontally.

═══════════════════════════════════════
ARROWS
═══════════════════════════════════════
Box bottom → next box top:
  x1 = box_x + 100   y1 = box_y + 56
  x2 = next_x + 100  y2 = next_y
  <line x1="..." y1="..." x2="..." y2="..." stroke="#888" stroke-width="1.5" marker-end="url(#arrow)"/>

From diamond BOTTOM (YES — continues main flow):
  x1=cx   y1=cy+40   x2=cx   y2=next_box_y
  <line x1="340" y1="240" x2="340" y2="310" stroke="#888" stroke-width="1.5" marker-end="url(#arrow)"/>
  <text x="352" y="278" font-family="sans-serif" font-size="11" font-weight="600" fill="#0a7a0a" dominant-baseline="central">Yes</text>

From diamond RIGHT or LEFT (NO — branch):
  x1=cx+90  y1=cy  x2=branch_box_x+100  y2=cy  (horizontal then down if needed)
  <line x1="430" y1="200" x2="540" y2="200" stroke="#888" stroke-width="1.5" marker-end="url(#arrow)"/>
  <text x="476" y="192" font-family="sans-serif" font-size="11" font-weight="600" fill="#cc0000" dominant-baseline="central">No</text>

For L-shaped routing (to avoid crossing boxes), use a path:
  <path d="M x1 y1 L x1 ymid L x2 ymid L x2 y2" fill="none" stroke="#888" stroke-width="1.5" marker-end="url(#arrow)"/>

CRITICAL: Every arrow that changes direction must use fill="none" on the path.

═══════════════════════════════════════
COLORS — meaning-based, not decorative
═══════════════════════════════════════
Use color to encode MEANING, not to decorate each step:

Blue:   fill="#E6F1FB" stroke="#185FA5" title="#0C447C" sub="#185FA5"   → neutral process steps
Purple: fill="#EEEDFE" stroke="#534AB7" title="#3C3489" sub="#534AB7"   → start / end nodes
Teal:   fill="#E1F5EE" stroke="#0F6E56" title="#085041" sub="#0F6E56"   → success / approve / done
Coral:  fill="#FAECE7" stroke="#993C1D" title="#712B13" sub="#993C1D"   → error / reject / fail
Amber:  fill="#FAEEDA" stroke="#854F0B" title="#633806" sub="#854F0B"   → decision diamonds / warning
Gray:   fill="#F1EFE8" stroke="#5F5E5A" title="#444441" sub="#5F5E5A"   → side steps / fallback

Rules:
- Use max 3 colors per diagram
- All nodes of the same TYPE get the same color
- Do NOT cycle rainbow colors across sequential steps

═══════════════════════════════════════
MISSING PATHS — COMMON FAILURE TO FIX
═══════════════════════════════════════
Every diamond MUST have BOTH a YES path AND a NO path drawn.
Both paths must eventually reach a terminal node or reconnect to main flow.
NEVER leave a diamond with only one exit arrow.

For the NO path — if it needs to skip nodes, route it:
  - horizontally to a side branch box, OR
  - with an L-bend path that routes AROUND existing boxes

If NO leads to the same place as YES (just skipping some steps):
  Draw the bypass line to the LEFT of the main column, then join back.

═══════════════════════════════════════
TEXT RULES
═══════════════════════════════════════
- Always add dominant-baseline="central" to every <text> inside a box or diamond
- font-size: 14px for titles, 12px for subtitles, 11px for arrow labels — nothing below 11px
- font-family="sans-serif" on every text element
- text-anchor="middle" for box/diamond labels
- Keep titles under ~20 characters. Keep subtitles under ~24 characters.
- Sentence case always. Never ALL CAPS or Title Case Every Word.
- SVG text never wraps. If text is long, shorten it — never let it overflow the box.

═══════════════════════════════════════
ARROW INTERSECTION CHECK
═══════════════════════════════════════
Before placing any arrow, check: does the line pass through any box it is NOT connecting?
If yes — route it around using an L-shaped <path> detour.
A line that slashes through an unrelated box is a broken diagram.

═══════════════════════════════════════
VIEWBOX HEIGHT CHECK
═══════════════════════════════════════
After placing all elements:
  Find the lowest element's bottom edge (y + height).
  Set viewBox H = that value + 40.
  Never guess. Never leave 300px of empty space at the bottom.

═══════════════════════════════════════
FINAL SELF-CHECK (run before closing </svg>)
═══════════════════════════════════════
1. Every diamond has YES arrow AND NO arrow, both labeled?
2. Every branch reconnects or ends at a terminal node?
3. No two boxes overlap?
4. No arrow passes through an unrelated box?
5. viewBox height fits all content with ~40px padding?
6. Response ends exactly with </svg> — nothing after it?
7. No markdown, no backticks, no English text outside SVG tags?

Output the SVG now. Only SVG. Nothing else."""


def save_log(prompt: str, svg: str) -> str:
    """
    Save every generated SVG to svg_logs/ folder.
    Returns the filename so we can log it to console.

    Two files per generation:
      1. svg_logs/image_YYYY-MM-DD_HH-MM-SS.svg  — the actual SVG
      2. svg_logs/log.txt                          — append-only history
         (timestamp + prompt + svg, separated by dashes)
    """
    now      = datetime.now()
    filename = now.strftime("image_%Y-%m-%d_%H-%M-%S.svg")
    svg_path = os.path.join(LOG_DIR, filename)
    log_path = os.path.join(LOG_DIR, "log.txt")

    # Save individual SVG file
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    # Append to master log (never overwrites — always appends)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"TIME   : {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"PROMPT : {prompt}\n")
        f.write(f"FILE   : {filename}\n")
        f.write(f"SVG    :\n{svg}\n")

    return filename


def is_svg_complete(svg: str) -> bool:
    """
    Check that the SVG is not truncated mid-way.
    A complete SVG must end with </svg> (case-insensitive, ignoring whitespace).
    """
    return svg.strip().lower().endswith("</svg>")


def extract_svg(text: str) -> str:
    """
    Robust SVG extraction — 5 strategies in order.
    Also validates that the extracted SVG is complete (not token-cut).
    """
    # Strategy 1 — strip <think>/<reasoning> blocks
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<reasoning>[\s\S]*?</reasoning>", "", text, flags=re.IGNORECASE)
    text = text.strip()

    # Strategy 2 — strip markdown fences
    text = re.sub(r"```(?:svg|xml)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Strategy 3 — greedy regex: first <svg to last </svg>
    match = re.search(r"(<svg[\s\S]*</svg>)", text, re.IGNORECASE)
    if match:
        svg = match.group(1).strip()
        if is_svg_complete(svg):
            return svg
        # SVG found but incomplete — token was cut
        return "<e>SVG was cut off mid-generation (token limit hit). Try a simpler diagram or fewer nodes.</e>"

    # Strategy 4 — text is already raw SVG
    if text.lower().startswith("<svg"):
        if is_svg_complete(text):
            return text.strip()
        return "<e>SVG was cut off mid-generation (token limit hit). Try a simpler diagram or fewer nodes.</e>"

    # Strategy 5 — find <svg anywhere in response
    idx = text.lower().find("<svg")
    if idx != -1:
        candidate = text[idx:]
        end = candidate.lower().rfind("</svg>")
        if end != -1:
            return candidate[:end + 6].strip()
        return "<e>SVG was cut off mid-generation (token limit hit). Try a simpler diagram or fewer nodes.</e>"

    preview = text[:400]
    return f"<e>Could not extract SVG. Raw response:\n{preview}</e>"


def call_sarvam_api(user_prompt: str) -> str:
    """Call Sarvam-M and return clean SVG."""
    headers = {
        "Authorization": f"Bearer {SARVAM_API_KEY}",
        "Content-Type":  "application/json"
    }
    payload = {
        "model":   MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Output SVG code only — no words, no explanation, "
                    f"start directly with <svg:\n\n{user_prompt}"
                )
            }
        ],
        "max_tokens":        8000,   # high limit — complex SVGs need 500+ lines
        "temperature":       0.1,    # very low for precise coordinates
        "include_reasoning": False   # skip <think> at API level
    }

    try:
        response = requests.post(
            SARVAM_API_URL,
            json=payload,
            headers=headers,
            timeout=120     # complex diagrams take longer
        )
        response.raise_for_status()
        data = response.json()
        raw  = data["choices"][0]["message"]["content"].strip()
        return extract_svg(raw)

    except requests.exceptions.HTTPError:
        return f"<e>API Error {response.status_code}: {response.text}</e>"
    except requests.exceptions.Timeout:
        return "<e>Request timed out. Try a simpler diagram.</e>"
    except Exception as e:
        return f"<e>Unexpected error: {str(e)}</e>"


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data   = request.get_json()
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return jsonify({"error": "Please enter a description"}), 400
    if len(prompt) > 1000:
        return jsonify({"error": "Description too long (max 1000 chars)"}), 400

    svg = call_sarvam_api(prompt)

    # Always log — even errors — so nothing is lost
    filename = save_log(prompt, svg)
    print(f"[LOG] Saved → {LOG_DIR}/{filename}")
    print(svg)  # also print to console for live debugging

    if svg.startswith("<e>"):
        msg = svg.replace("<e>", "").replace("</e>", "")
        return jsonify({"error": msg}), 500

    return jsonify({"svg": svg})


if __name__ == "__main__":
    print("=" * 50)
    print("  SVG Diagram Generator — Sarvam-M")
    print(f"  Logs → ./{LOG_DIR}/")
    print("  URL  → http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)