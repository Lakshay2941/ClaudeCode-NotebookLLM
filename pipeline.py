"""
Research → NotebookLM Pipeline
-------------------------------
Orchestrates the full workflow:
  1. Search YouTube for a topic (yt-research skill)
  2. Create a NotebookLM notebook
  3. Upload the top N video URLs as sources
  4. Ask NotebookLM for an analysis summary
  5. Generate a deliverable (infographic, slides, flashcards, or report)

Usage:
    python pipeline.py --topic "AI agents 2025" --count 25 --deliverable infographic
    python pipeline.py --topic "machine learning trends" --deliverable slides
    python pipeline.py --topic "deep learning" --deliverable flashcards
    python pipeline.py --topic "LLM fine-tuning" --deliverable report

Deliverable choices:
    infographic  – handwritten/chalkboard style (SKETCH_NOTE) by default
    slides       – detailed slide deck
    flashcards   – study flashcards
    report       – briefing document

The pipeline is also callable programmatically:
    import asyncio
    from pipeline import run_pipeline
    asyncio.run(run_pipeline(topic="AI agents 2025", count=25, deliverable="infographic"))
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from skills.notebooklm_skill import NotebookLMSkill
from skills.yt_research import search_youtube

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

ANALYSIS_QUESTION = (
    "You have been given {count} YouTube videos about '{topic}'. "
    "Please analyse their content and provide: "
    "(1) The top 5–7 key findings or trends, "
    "(2) What topics come up most frequently, "
    "(3) Any surprising or counterintuitive insights, "
    "(4) A recommended reading/watching order if someone wants to learn the most efficiently."
)

INFOGRAPHIC_INSTRUCTIONS = (
    "Create a visually engaging infographic summarising the top findings from these YouTube videos "
    "about '{topic}'. Use a handwritten / chalkboard aesthetic. "
    "Highlight the most important trends, include key statistics where available, "
    "and make it feel like a smart student's notes on a blackboard."
)


async def run_pipeline(
    topic: str,
    count: int = 25,
    deliverable: str = "infographic",
    no_check_certificate: bool = False,
) -> dict:
    """Run the full research pipeline.

    Args:
        topic: The YouTube search topic.
        count: Number of videos to fetch.
        deliverable: One of 'infographic', 'slides', 'flashcards', 'report'.
        no_check_certificate: Pass-through to yt-dlp for SSL issues.

    Returns:
        Dict with keys: notebook_id, analysis, artifact_path, video_urls
    """
    print(f"\n{'='*60}")
    print(f"  PIPELINE: {topic!r}  |  top {count} videos  |  {deliverable}")
    print(f"{'='*60}\n")

    # ── Step 1: YouTube research ──────────────────────────────────────
    print("► Step 1/4  Searching YouTube…")
    videos = search_youtube(topic, count=count, no_check_certificate=no_check_certificate)
    if not videos:
        raise RuntimeError(
            "YouTube search returned no results. "
            "Check your internet connection and try again."
        )

    print(f"  Found {len(videos)} videos.")
    for v in videos[:5]:
        print(f"    {v.rank:>2}. {v.title[:70]}")
    if len(videos) > 5:
        print(f"    … and {len(videos) - 5} more")

    video_urls = [v.url for v in videos]
    urls_path = OUTPUT_DIR / "video_urls.json"
    urls_path.write_text(json.dumps(video_urls, indent=2))
    print(f"  URL list saved → {urls_path}")

    # ── Steps 2–5: NotebookLM ─────────────────────────────────────────
    async with NotebookLMSkill() as nlm:
        # Step 2: Create notebook
        print(f"\n► Step 2/4  Creating NotebookLM notebook…")
        notebook_title = f"YT Research: {topic[:60]}"
        nb = await nlm.create_notebook(notebook_title)

        # Step 3: Upload sources
        print(f"\n► Step 3/4  Uploading {len(video_urls)} YouTube sources…")
        await nlm.add_youtube_urls(nb.id, video_urls, wait=True)

        # Step 4: Analysis
        print(f"\n► Step 4/4  Requesting analysis…")
        question = ANALYSIS_QUESTION.format(count=len(videos), topic=topic)
        analysis = await nlm.ask(nb.id, question)
        print("\n── Analysis ──────────────────────────────────────────")
        print(analysis)
        print("──────────────────────────────────────────────────────\n")

        analysis_path = OUTPUT_DIR / "analysis.txt"
        analysis_path.write_text(analysis, encoding="utf-8")
        print(f"  Analysis saved → {analysis_path}")

        # Step 5: Deliverable
        artifact_path: Path | None = None
        instr = INFOGRAPHIC_INSTRUCTIONS.format(topic=topic)

        if deliverable == "infographic":
            artifact_path = await nlm.generate_infographic(
                nb.id,
                style="SKETCH_NOTE",
                orientation="LANDSCAPE",
                detail="DETAILED",
                instructions=instr,
                output_name=f"infographic_{topic[:30].replace(' ', '_')}",
            )
        elif deliverable == "slides":
            artifact_path = await nlm.generate_slide_deck(
                nb.id,
                slide_format="DETAILED_DECK",
                instructions=f"Create slides summarising the key findings about '{topic}' from these YouTube videos.",
                output_name=f"slides_{topic[:30].replace(' ', '_')}",
            )
        elif deliverable == "flashcards":
            artifact_path = await nlm.generate_flashcards(
                nb.id,
                instructions=f"Create flashcards covering the key concepts and findings about '{topic}'.",
                output_name=f"flashcards_{topic[:30].replace(' ', '_')}",
            )
        elif deliverable == "report":
            artifact_path = await nlm.generate_report(
                nb.id,
                report_format="BRIEFING_DOC",
                custom_prompt=f"Write a briefing document on the state of '{topic}' based on these YouTube videos.",
                output_name=f"report_{topic[:30].replace(' ', '_')}",
            )
        else:
            print(f"Unknown deliverable {deliverable!r}, skipping artifact generation.")

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    if artifact_path:
        print(f"  Artifact  → {artifact_path}")
    print(f"  Analysis  → {analysis_path}")
    print(f"  URLs      → {urls_path}")
    print(f"{'='*60}\n")

    return {
        "notebook_id": nb.id,
        "analysis": analysis,
        "artifact_path": str(artifact_path) if artifact_path else None,
        "video_urls": video_urls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube → NotebookLM research pipeline"
    )
    parser.add_argument(
        "--topic", "-t",
        required=True,
        help="YouTube search topic",
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=25,
        help="Number of videos to research (default 25)",
    )
    parser.add_argument(
        "--deliverable", "-d",
        default="infographic",
        choices=["infographic", "slides", "flashcards", "report"],
        help="Type of artifact to generate (default: infographic)",
    )
    parser.add_argument(
        "--no-check-certificate",
        action="store_true",
        dest="no_check_certificate",
        help="Skip SSL certificate verification",
    )
    args = parser.parse_args()
    asyncio.run(
        run_pipeline(
            topic=args.topic,
            count=args.count,
            deliverable=args.deliverable,
            no_check_certificate=args.no_check_certificate,
        )
    )


if __name__ == "__main__":
    main()
