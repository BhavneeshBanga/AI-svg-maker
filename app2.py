from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from datetime import datetime
import requests
import re
import os

load_dotenv()

app = Flask(__name__)

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_API_URL = "https://api.sarvam.ai/v1/chat/completions"
MODEL          = "sarvam-m"

LOG_DIR = "svg_logs"
os.makedirs(LOG_DIR, exist_ok=True)

if not SARVAM_API_KEY:
    raise EnvironmentError(
        "\n\n  SARVAM_API_KEY not found!"
        "\n  Add this to your .env file:"
        "\n  SARVAM_API_KEY=your_actual_key_here\n"
    )

# ── System prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an SVG flowchart generator. Output only raw SVG. No explanation. No markdown. No backticks. Start with <svg and end with </svg>.

═══════════════════════════════════
CANVAS
═══════════════════════════════════
<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 680 H">

viewBox width is ALWAYS 680. Never change it.
Set H based on row count:
  ≤4 rows  → H = 500
  5–7      → H = 700
  8–11     → H = 950
  12+      → H = 1250

═══════════════════════════════════
ALWAYS START WITH THIS <defs>
═══════════════════════════════════
<defs>
  <style>
    @keyframes fadeSlideIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes drawLine {
      from { stroke-dashoffset: 1; }
      to   { stroke-dashoffset: 0; }
    }
    .node-anim {
      opacity: 0;
      animation: fadeSlideIn 0.4s ease forwards;
    }
    .arrow-anim {
      stroke-dasharray: 1;
      stroke-dashoffset: 1;
      pathLength: 1;
      animation: drawLine 0.3s ease forwards;
    }
  </style>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>

═══════════════════════════════════
ANIMATION RULES
═══════════════════════════════════
Every box group gets class="node-anim" and an animation-delay.
Every arrow line gets class="arrow-anim" and an animation-delay.

Stagger delay by 0.15s per element, top to bottom:
  First box:   animation-delay: 0.1s
  First arrow: animation-delay: 0.25s
  Second box:  animation-delay: 0.35s
  Second arrow:animation-delay: 0.5s
  ... and so on (each element = previous + 0.15s)

CORRECT box group with animation:
<g class="node-anim" style="animation-delay: 0.1s">
  <rect x="240" y="40" width="200" height="56" rx="8" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
  <text x="340" y="60" font-family="sans-serif" font-size="14" font-weight="500" fill="#0C447C" text-anchor="middle" dominant-baseline="central">Box title</text>
  <text x="340" y="78" font-family="sans-serif" font-size="12" fill="#185FA5" text-anchor="middle" dominant-baseline="central">subtitle here</text>
</g>

CORRECT arrow with animation:
<line class="arrow-anim" style="animation-delay: 0.25s" x1="340" y1="96" x2="340" y2="140" stroke="#888" stroke-width="1.5" marker-end="url(#arrow)" pathLength="1"/>

Note: pathLength="1" is required on every animated arrow line.

═══════════════════════════════════
BOX TEMPLATE
═══════════════════════════════════
Size: width=200 height=56 rx=8
Main column center: x=340 → rect x=240

Title  y = box_y + 20   dominant-baseline="central"   font-size="14" font-weight="500"
Sub    y = box_y + 38   dominant-baseline="central"   font-size="12" font-weight="400"
Both:  text-anchor="middle"   x = box_x + 100

Never put two texts at the same y — they will overlap.

═══════════════════════════════════
DIAMOND TEMPLATE
═══════════════════════════════════
Center (cx, cy). Half-width=90, half-height=40.
Points: (cx,cy-40)  (cx+90,cy)  (cx,cy+40)  (cx-90,cy)

Wrap diamond in animation group:
<g class="node-anim" style="animation-delay: 0.35s">
  <polygon points="340,160 430,200 340,240 250,200" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
  <text x="340" y="197" font-family="sans-serif" font-size="13" font-weight="500" fill="#633806" text-anchor="middle" dominant-baseline="central">Decision?</text>
</g>

NEVER have TOP and RIGHT at the same y (flat line, not diamond).

═══════════════════════════════════
LAYOUT GRID
═══════════════════════════════════
Main column: x=340 (rect x=240)
Left branch: x=130 (rect x=30)
Right branch:x=570 (rect x=470)

Vertical step = 110px per row.
Row 1: y=30  Row 2: y=140  Row 3: y=250 ...

═══════════════════════════════════
COLORS (meaning-based)
═══════════════════════════════════
Blue:   fill="#E6F1FB" stroke="#185FA5" title="#0C447C" sub="#185FA5"   → process steps
Purple: fill="#EEEDFE" stroke="#534AB7" title="#3C3489" sub="#534AB7"   → start / end
Teal:   fill="#E1F5EE" stroke="#0F6E56" title="#085041" sub="#0F6E56"   → success / done
Coral:  fill="#FAECE7" stroke="#993C1D" title="#712B13" sub="#993C1D"   → error / fail
Amber:  fill="#FAEEDA" stroke="#854F0B" title="#633806" sub="#854F0B"   → decisions
Gray:   fill="#F1EFE8" stroke="#5F5E5A" title="#444441" sub="#5F5E5A"   → fallback / side

Use max 3 colors. Same node TYPE = same color.

═══════════════════════════════════
ARROWS
═══════════════════════════════════
<line class="arrow-anim" style="animation-delay: Xs"
  x1="..." y1="..." x2="..." y2="..."
  stroke="#888" stroke-width="1.5"
  marker-end="url(#arrow)" pathLength="1"/>

YES label (green):
<text x="..." y="..." font-family="sans-serif" font-size="11" font-weight="600" fill="#0a7a0a" dominant-baseline="central">Yes</text>

NO label (red):
<text x="..." y="..." font-family="sans-serif" font-size="11" font-weight="600" fill="#cc0000" dominant-baseline="central">No</text>

For L-shaped routing: <path class="arrow-anim" style="animation-delay: Xs" d="M x1 y1 L x1 ymid L x2 ymid L x2 y2" fill="none" stroke="#888" stroke-width="1.5" marker-end="url(#arrow)" pathLength="1"/>

═══════════════════════════════════
DIAMOND EXIT RULE
═══════════════════════════════════
Every diamond MUST have BOTH a YES arrow AND a NO arrow.
Both must reach a terminal node or rejoin the main flow.
Never leave a diamond with only one exit.

NO path that bypasses nodes:
  Route it LEFT of the main column using L-shaped path.
  Then join back to the flow below the skipped nodes.

═══════════════════════════════════
FINAL CHECK
═══════════════════════════════════
1. Every diamond has YES + NO arrow, both labeled?
2. Every branch reconnects or ends at a terminal?
3. Every box group has class="node-anim" + animation-delay?
4. Every arrow line/path has class="arrow-anim" + animation-delay + pathLength="1"?
5. No two boxes overlap?
6. No arrow passes through an unrelated box?
7. viewBox height fits all content + 40px buffer?
8. Response ends exactly with </svg>?

Output SVG only. Nothing else."""


# ── Animation post-processor ──────────────────────────────────────────
def inject_animations(svg: str) -> str:
    """
    Fallback: if the LLM forgot to add animations, inject them via JS
    into a <script> tag at the end of the SVG. This animates every
    rect, polygon, line, and path inside the SVG on load.

    If the LLM already added CSS @keyframes (class="node-anim"), this
    script detects that and skips itself to avoid double-animation.
    """
    if not svg.strip().lower().endswith("</svg>"):
        return svg  # broken SVG, don't touch it

    animation_script = """
<script type="text/javascript">
(function() {
  var svg = document.currentScript.closest('svg') || document.querySelector('svg');
  if (!svg) return;
  // If LLM already added CSS animations, skip JS fallback
  if (svg.querySelector('.node-anim')) return;

  var elements = svg.querySelectorAll('rect, polygon, line, path, circle, ellipse, text');
  var delay = 0;
  elements.forEach(function(el) {
    var tag = el.tagName.toLowerCase();
    // Skip defs, markers, style, and tiny decorative elements
    if (el.closest('defs') || el.closest('marker')) return;
    if (tag === 'path' && !el.getAttribute('stroke')) return;

    el.style.opacity = '0';
    el.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
    el.style.transform = 'translateY(8px)';

    var d = delay;
    setTimeout(function() {
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, d);

    delay += 60; // 60ms stagger between each element
  });
})();
</script>
"""
    # Inject before closing </svg>
    return svg.rstrip().rstrip("</svg>").rstrip() + animation_script + "\n</svg>"


def save_log(prompt: str, svg: str) -> str:
    now      = datetime.now()
    filename = now.strftime("image_%Y-%m-%d_%H-%M-%S.svg")
    svg_path = os.path.join(LOG_DIR, filename)
    log_path = os.path.join(LOG_DIR, "log.txt")

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"TIME   : {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"PROMPT : {prompt}\n")
        f.write(f"FILE   : {filename}\n")
        f.write(f"SVG    :\n{svg}\n")

    return filename


def is_svg_complete(svg: str) -> bool:
    return svg.strip().lower().endswith("</svg>")


def extract_svg(text: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<reasoning>[\s\S]*?</reasoning>", "", text, flags=re.IGNORECASE)
    text = text.strip()

    text = re.sub(r"```(?:svg|xml)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    match = re.search(r"(<svg[\s\S]*</svg>)", text, re.IGNORECASE)
    if match:
        svg = match.group(1).strip()
        if is_svg_complete(svg):
            return svg
        return "<e>SVG was cut off mid-generation. Try a simpler diagram.</e>"

    if text.lower().startswith("<svg"):
        if is_svg_complete(text):
            return text.strip()
        return "<e>SVG was cut off mid-generation. Try a simpler diagram.</e>"

    idx = text.lower().find("<svg")
    if idx != -1:
        candidate = text[idx:]
        end = candidate.lower().rfind("</svg>")
        if end != -1:
            return candidate[:end + 6].strip()
        return "<e>SVG was cut off mid-generation. Try a simpler diagram.</e>"

    preview = text[:400]
    return f"<e>Could not extract SVG. Raw response:\n{preview}</e>"


def call_sarvam_api(user_prompt: str) -> str:
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
        "max_tokens":        8000,
        "temperature":       0.1,
        "include_reasoning": False
    }

    try:
        response = requests.post(
            SARVAM_API_URL,
            json=payload,
            headers=headers,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        raw  = data["choices"][0]["message"]["content"].strip()
        svg  = extract_svg(raw)

        # Inject animations (CSS-based if LLM added them, JS fallback otherwise)
        if not svg.startswith("<e>"):
            svg = inject_animations(svg)

        return svg

    except requests.exceptions.HTTPError:
        return f"<e>API Error {response.status_code}: {response.text}</e>"
    except requests.exceptions.Timeout:
        return "<e>Request timed out. Try a simpler diagram.</e>"
    except Exception as e:
        return f"<e>Unexpected error: {str(e)}</e>"


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

    filename = save_log(prompt, svg)
    print(f"[LOG] Saved → {LOG_DIR}/{filename}")
    print(svg)

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