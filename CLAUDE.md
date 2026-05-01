# ClaudeCode-NotebookLM Pipeline

Automated research pipeline connecting Claude Code to Google NotebookLM.

## Project Layout

```
ClaudeCode-NotebookLLM/
├── skills/
│   ├── yt_research.py        # YouTube metadata scraper (yt-dlp)
│   └── notebooklm_skill.py   # NotebookLM async wrapper
├── pipeline.py               # End-to-end orchestrator
├── output/                   # Generated artifacts land here
└── requirements.txt
```

## Dependencies

```
pip install -r requirements.txt
```

Packages: `yt-dlp`, `notebooklm-py`

---

## Authentication (required before first use)

Run **once** in a separate terminal window:

```bash
notebooklm login
```

This opens a browser for Google OAuth and saves credentials to
`~/.config/notebooklm/auth.json`. Claude will use these credentials
automatically for all subsequent NotebookLM operations.

---

## Skill: yt-research

Search YouTube and return video metadata (title, author, views, duration, URL).
No API key required — uses yt-dlp under the hood.

### How Claude uses it

When you say **"use the yt-research skill"**, Claude will call `search_youtube()`
from `skills/yt_research.py`.

**If no topic is given, Claude will ask you for one before proceeding.**

### CLI

```bash
# Print results to terminal
python skills/yt_research.py --query "AI agents 2025" --count 25

# Output as JSON
python skills/yt_research.py --query "AI agents 2025" --count 25 --json

# Save JSON to file
python skills/yt_research.py --query "AI agents 2025" --count 25 --output output/results.json

# Behind a corporate proxy / self-signed cert
python skills/yt_research.py --query "AI agents 2025" --count 25 --no-check-certificate
```

### Python API

```python
from skills.yt_research import search_youtube

videos = search_youtube("AI agents 2025", count=25)
for v in videos:
    print(v.rank, v.title, v.url, v.views, v.duration_str)
```

### VideoResult fields

| Field | Type | Description |
|-------|------|-------------|
| rank | int | Position in results |
| title | str | Video title |
| url | str | YouTube watch URL |
| author | str | Channel / uploader name |
| views | int\|None | View count |
| duration_seconds | int\|None | Length in seconds |
| duration_str | str | Human-readable length (e.g. `12:34`) |
| upload_date | str\|None | YYYYMMDD |
| thumbnail | str\|None | Thumbnail URL |

---

## Skill: notebooklm

Async wrapper around `notebooklm-py` for creating notebooks, uploading sources,
and generating AI deliverables.

### How Claude uses it

When you say **"send them over to NotebookLM"** or **"use the notebooklm skill"**,
Claude will use `skills/notebooklm_skill.py`.

### CLI

```bash
# Create a notebook
python skills/notebooklm_skill.py create --title "AI Research"

# List notebooks
python skills/notebooklm_skill.py list

# Add YouTube URLs (space-separated or from a file)
python skills/notebooklm_skill.py add-sources --notebook-id <ID> \
    --urls "https://youtu.be/abc" "https://youtu.be/xyz"

python skills/notebooklm_skill.py add-sources --notebook-id <ID> \
    --urls-file output/video_urls.json

# Ask a question
python skills/notebooklm_skill.py ask --notebook-id <ID> \
    --question "What are the top trends in this content?"

# Generate infographic (handwritten/chalkboard = SKETCH_NOTE)
python skills/notebooklm_skill.py infographic --notebook-id <ID> \
    --style SKETCH_NOTE --orientation LANDSCAPE --detail DETAILED

# Generate slide deck
python skills/notebooklm_skill.py slides --notebook-id <ID>

# Generate flashcards
python skills/notebooklm_skill.py flashcards --notebook-id <ID>

# Generate briefing report
python skills/notebooklm_skill.py report --notebook-id <ID>
```

### Infographic styles

| Style name | Description |
|------------|-------------|
| `SKETCH_NOTE` | Handwritten / chalkboard look **(default for this pipeline)** |
| `PROFESSIONAL` | Clean corporate style |
| `BENTO_GRID` | Japanese bento-box grid layout |
| `EDITORIAL` | Magazine editorial |
| `INSTRUCTIONAL` | Step-by-step instructional |
| `BRICKS` | Brick/tile layout |
| `CLAY` | 3D clay-style illustration |
| `ANIME` | Anime-inspired |
| `KAWAII` | Cute kawaii |
| `SCIENTIFIC` | Data-heavy scientific |
| `AUTO` | Let NotebookLM choose |

---

## Pipeline: end-to-end

```bash
# Full pipeline: research + analyse + generate infographic
python pipeline.py --topic "AI agents 2025" --count 25 --deliverable infographic

# Other deliverables
python pipeline.py --topic "machine learning trends" --deliverable slides
python pipeline.py --topic "deep learning" --deliverable flashcards
python pipeline.py --topic "LLM fine-tuning" --deliverable report
```

Output lands in `./output/`:
- `video_urls.json` — all discovered URLs
- `analysis.txt` — NotebookLM's written analysis
- `infographic_<topic>.*` / `slides_<topic>.*` / etc. — the generated artifact

---

## Claude's command grammar

When the user says something like:

> "Use the yt-research skill to find the 25 latest trending videos on [TOPIC].
> Once we have those videos, send them over to NotebookLM using the notebooklm
> skill. Give me its analysis on the top findings, then have NotebookLM create
> an infographic in a handwritten / chalkboard style depicting that analysis."

Claude should:
1. **If no topic is given** — ask the user: "What topic would you like me to research?"
2. Call `search_youtube(topic, count=25)` using `skills/yt_research.py`
3. Display the top results
4. Call `pipeline.run_pipeline(topic, count, deliverable="infographic")` which:
   - Creates a notebook
   - Uploads all URLs as sources
   - Requests analysis
   - Generates a `SKETCH_NOTE` infographic

For "chalkboard / handwritten" style → always use `style="SKETCH_NOTE"`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `AuthError` from NotebookLM | Run `notebooklm login` in a terminal |
| YouTube 403 / SSL error | Add `--no-check-certificate` flag |
| Source processing timeout | Reduce `--count`, NotebookLM has a source limit |
| Artifact not ready | Generation can take 1–5 min; pipeline waits up to 5 min |
