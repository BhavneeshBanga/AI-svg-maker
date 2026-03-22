# SVG Diagram Generator — Powered by Sarvam-M

A Flask web app that turns plain English descriptions into SVG diagrams using the Sarvam-M LLM API.

## Setup (3 steps)

### Step 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Add your Sarvam API key
Open `app.py` and replace line 10:
```python
SARVAM_API_KEY = "YOUR_API_KEY_HERE"
```
with your actual key. Or set it as an environment variable:
```bash
# Windows
set SARVAM_API_KEY=your_actual_key_here

# Mac/Linux
export SARVAM_API_KEY=your_actual_key_here
```

### Step 3 — Run the app
```bash
python app.py
```
Then open http://localhost:5000 in your browser.

## How It Works

```
User types description
        ↓
Flask receives POST /generate
        ↓
Sends to Sarvam-M API with a detailed system prompt
(the system prompt teaches the LLM how to draw SVG)
        ↓
LLM returns SVG code
        ↓
Python extracts clean SVG (removes any markdown wrapping)
        ↓
Frontend renders it in the browser
User can copy / download the SVG
```

## Project Structure

```
svg_generator/
├── app.py              ← Flask backend + Sarvam API call
├── requirements.txt    ← Python dependencies
├── README.md           ← This file
└── templates/
    └── index.html      ← Frontend UI
```

## Key Concepts

- **System Prompt Engineering**: The `SYSTEM_PROMPT` in `app.py` is the most
  important part. It teaches the LLM the exact SVG rules, coordinate system,
  colors, and layout logic to follow. Better prompt = better diagrams.

- **SVG Extraction**: LLMs sometimes wrap output in ```svg blocks or add
  extra explanation text. The `extract_svg()` function cleans that up using
  regex so we always get pure SVG.

- **Temperature 0.3**: Low temperature makes the LLM more precise and
  consistent — important for coordinate math.

## Customization Ideas

1. Add more example prompts in index.html chips
2. Add a "style selector" (flowchart / mindmap / timeline) 
3. Save generated diagrams to a gallery
4. Add PNG export using a headless browser
5. Let users regenerate with "make it bigger" / "add more steps" follow-ups