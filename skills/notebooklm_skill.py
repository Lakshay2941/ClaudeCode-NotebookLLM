"""
NotebookLM Skill
----------------
Async wrapper around notebooklm-py that lets Claude:
  • Create notebooks
  • Upload YouTube URLs as sources (batch or single)
  • Request analysis via chat
  • Generate deliverables: infographics, slide decks, flashcards, reports
  • Download generated artifacts to ./output/

Authentication:
    Run once in a separate terminal:
        notebooklm login
    This saves credentials to ~/.config/notebooklm/auth.json

CLI usage:
    # Create a notebook and upload URLs
    python skills/notebooklm_skill.py create --title "AI Research"
    python skills/notebooklm_skill.py add-sources --notebook-id <ID> --urls urls.txt
    python skills/notebooklm_skill.py ask --notebook-id <ID> --question "What are the top trends?"
    python skills/notebooklm_skill.py infographic --notebook-id <ID> --style SKETCH_NOTE
    python skills/notebooklm_skill.py slides --notebook-id <ID>
    python skills/notebooklm_skill.py flashcards --notebook-id <ID>

Programmatic usage:
    import asyncio
    from skills.notebooklm_skill import NotebookLMSkill

    async def run():
        async with NotebookLMSkill() as nlm:
            nb = await nlm.create_notebook("AI Research")
            sources = await nlm.add_youtube_urls(nb.id, ["https://youtu.be/..."])
            answer = await nlm.ask(nb.id, "What are the key insights?")
            path = await nlm.generate_infographic(nb.id, style="SKETCH_NOTE")
    asyncio.run(run())
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient
from notebooklm.rpc.types import (
    InfographicDetail,
    InfographicOrientation,
    InfographicStyle,
    ReportFormat,
    SlideDeckFormat,
    SlideDeckLength,
)
from notebooklm.types import GenerationStatus, Notebook, Source

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Maps friendly style names to enum values for the infographic generator
INFOGRAPHIC_STYLE_MAP: dict[str, InfographicStyle] = {
    "AUTO": InfographicStyle.AUTO_SELECT,
    "SKETCH_NOTE": InfographicStyle.SKETCH_NOTE,   # closest to chalkboard/handwritten
    "PROFESSIONAL": InfographicStyle.PROFESSIONAL,
    "BENTO_GRID": InfographicStyle.BENTO_GRID,
    "EDITORIAL": InfographicStyle.EDITORIAL,
    "INSTRUCTIONAL": InfographicStyle.INSTRUCTIONAL,
    "BRICKS": InfographicStyle.BRICKS,
    "CLAY": InfographicStyle.CLAY,
    "ANIME": InfographicStyle.ANIME,
    "KAWAII": InfographicStyle.KAWAII,
    "SCIENTIFIC": InfographicStyle.SCIENTIFIC,
}


class NotebookLMSkill:
    """High-level async skill wrapping NotebookLMClient."""

    def __init__(self) -> None:
        self._client: NotebookLMClient | None = None
        self._raw_client: NotebookLMClient | None = None

    async def __aenter__(self) -> "NotebookLMSkill":
        # from_storage() is async — await it to get the client instance,
        # then separately enter its async context manager.
        self._raw_client = await NotebookLMClient.from_storage()
        self._client = await self._raw_client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._raw_client:
            await self._raw_client.__aexit__(*args)

    # ------------------------------------------------------------------
    # Notebook management
    # ------------------------------------------------------------------

    async def create_notebook(self, title: str) -> Notebook:
        """Create a new notebook and return it."""
        assert self._client
        nb = await self._client.notebooks.create(title)
        print(f"Created notebook: {nb.title!r}  (id={nb.id})")
        return nb

    async def list_notebooks(self) -> list[Notebook]:
        """List all notebooks."""
        assert self._client
        return await self._client.notebooks.list()

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    async def add_youtube_urls(
        self,
        notebook_id: str,
        urls: list[str],
        wait: bool = True,
    ) -> list[Source]:
        """Add a list of YouTube URLs to a notebook.

        Args:
            notebook_id: Target notebook ID.
            urls: YouTube watch URLs.
            wait: Block until each source is processed (recommended).

        Returns:
            List of created Source objects.
        """
        assert self._client
        sources: list[Source] = []
        total = len(urls)
        for i, url in enumerate(urls, 1):
            print(f"  [{i}/{total}] Adding source: {url}")
            try:
                src = await self._client.sources.add_url(
                    notebook_id, url, wait=wait, wait_timeout=180.0
                )
                sources.append(src)
            except Exception as exc:
                print(f"    WARNING: Failed to add {url}: {exc}", file=sys.stderr)
        print(f"Added {len(sources)}/{total} sources.")
        return sources

    # ------------------------------------------------------------------
    # Chat / analysis
    # ------------------------------------------------------------------

    async def ask(self, notebook_id: str, question: str) -> str:
        """Ask a question and return the text response."""
        assert self._client
        result = await self._client.chat.ask(notebook_id, question)
        # result may be a string or an object with .text
        if isinstance(result, str):
            return result
        return getattr(result, "text", str(result))

    # ------------------------------------------------------------------
    # Artifact generation
    # ------------------------------------------------------------------

    async def generate_infographic(
        self,
        notebook_id: str,
        style: str = "SKETCH_NOTE",
        orientation: str = "LANDSCAPE",
        detail: str = "DETAILED",
        instructions: str | None = None,
        output_name: str = "infographic",
    ) -> Path | None:
        """Generate an infographic and download it.

        Args:
            notebook_id: Target notebook.
            style: One of SKETCH_NOTE, PROFESSIONAL, BENTO_GRID, EDITORIAL,
                   INSTRUCTIONAL, BRICKS, CLAY, ANIME, KAWAII, SCIENTIFIC, AUTO.
            orientation: LANDSCAPE, PORTRAIT, or SQUARE.
            detail: CONCISE, STANDARD, or DETAILED.
            instructions: Optional freeform generation instructions.
            output_name: Base filename (without extension) for the download.

        Returns:
            Path to the downloaded file, or None on failure.
        """
        assert self._client

        style_enum = INFOGRAPHIC_STYLE_MAP.get(style.upper(), InfographicStyle.SKETCH_NOTE)
        orientation_enum = InfographicOrientation[orientation.upper()]
        detail_enum = InfographicDetail[detail.upper()]

        print(f"Generating infographic (style={style}, orientation={orientation}, detail={detail})…")
        status: GenerationStatus = await self._client.artifacts.generate_infographic(
            notebook_id,
            style=style_enum,
            orientation=orientation_enum,
            detail_level=detail_enum,
            instructions=instructions,
        )
        print(f"  Waiting for completion (task_id={status.task_id})…")
        final = await self._client.artifacts.wait_for_completion(
            notebook_id, status.task_id, timeout=300.0
        )
        return await self._download_artifact(notebook_id, final, output_name)

    async def generate_slide_deck(
        self,
        notebook_id: str,
        slide_format: str = "DETAILED_DECK",
        instructions: str | None = None,
        output_name: str = "slides",
    ) -> Path | None:
        """Generate a slide deck and download it."""
        assert self._client

        fmt_enum = SlideDeckFormat[slide_format.upper()]
        print(f"Generating slide deck (format={slide_format})…")
        status = await self._client.artifacts.generate_slide_deck(
            notebook_id,
            slide_format=fmt_enum,
            instructions=instructions,
        )
        print(f"  Waiting for completion (task_id={status.task_id})…")
        final = await self._client.artifacts.wait_for_completion(
            notebook_id, status.task_id, timeout=300.0
        )
        return await self._download_artifact(notebook_id, final, output_name)

    async def generate_flashcards(
        self,
        notebook_id: str,
        instructions: str | None = None,
        output_name: str = "flashcards",
    ) -> Path | None:
        """Generate flashcards and download them."""
        assert self._client

        print("Generating flashcards…")
        status = await self._client.artifacts.generate_flashcards(
            notebook_id,
            instructions=instructions,
        )
        print(f"  Waiting for completion (task_id={status.task_id})…")
        final = await self._client.artifacts.wait_for_completion(
            notebook_id, status.task_id, timeout=300.0
        )
        return await self._download_artifact(notebook_id, final, output_name)

    async def generate_report(
        self,
        notebook_id: str,
        report_format: str = "BRIEFING_DOC",
        custom_prompt: str | None = None,
        output_name: str = "report",
    ) -> Path | None:
        """Generate a report (briefing doc, study guide, blog post, or custom)."""
        assert self._client

        fmt_map = {
            "BRIEFING_DOC": ReportFormat.BRIEFING_DOC,
            "STUDY_GUIDE": ReportFormat.STUDY_GUIDE,
            "BLOG_POST": ReportFormat.BLOG_POST,
            "CUSTOM": ReportFormat.CUSTOM,
        }
        fmt_enum = fmt_map.get(report_format.upper(), ReportFormat.BRIEFING_DOC)
        print(f"Generating report (format={report_format})…")
        status = await self._client.artifacts.generate_report(
            notebook_id,
            report_format=fmt_enum,
            custom_prompt=custom_prompt,
        )
        print(f"  Waiting for completion (task_id={status.task_id})…")
        final = await self._client.artifacts.wait_for_completion(
            notebook_id, status.task_id, timeout=300.0
        )
        return await self._download_artifact(notebook_id, final, output_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _download_artifact(
        self, notebook_id: str, status: GenerationStatus, name: str
    ) -> Path | None:
        assert self._client
        if not getattr(status, "completed", False):
            print(f"  WARNING: artifact did not complete — status: {status}", file=sys.stderr)
            return None
        try:
            artifact = await self._client.artifacts.get(notebook_id, status.task_id)
            dest = OUTPUT_DIR / name
            saved = await self._client.artifacts.download(artifact, dest)
            print(f"  Saved artifact → {saved}")
            return Path(saved)
        except Exception as exc:
            print(f"  WARNING: could not download artifact: {exc}", file=sys.stderr)
            return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NotebookLM Skill CLI — create notebooks, add sources, generate content."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new notebook")
    p_create.add_argument("--title", required=True)

    # list
    sub.add_parser("list", help="List all notebooks")

    # add-sources
    p_add = sub.add_parser("add-sources", help="Add YouTube URLs to a notebook")
    p_add.add_argument("--notebook-id", required=True)
    p_add.add_argument(
        "--urls",
        nargs="*",
        help="Space-separated YouTube URLs",
    )
    p_add.add_argument(
        "--urls-file",
        help="Text file with one YouTube URL per line",
    )

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question about the notebook")
    p_ask.add_argument("--notebook-id", required=True)
    p_ask.add_argument("--question", required=True)

    # infographic
    p_inf = sub.add_parser("infographic", help="Generate an infographic")
    p_inf.add_argument("--notebook-id", required=True)
    p_inf.add_argument(
        "--style",
        default="SKETCH_NOTE",
        choices=list(INFOGRAPHIC_STYLE_MAP.keys()),
    )
    p_inf.add_argument(
        "--orientation",
        default="LANDSCAPE",
        choices=["LANDSCAPE", "PORTRAIT", "SQUARE"],
    )
    p_inf.add_argument(
        "--detail",
        default="DETAILED",
        choices=["CONCISE", "STANDARD", "DETAILED"],
    )
    p_inf.add_argument("--instructions", default=None)
    p_inf.add_argument("--output-name", default="infographic")

    # slides
    p_slides = sub.add_parser("slides", help="Generate a slide deck")
    p_slides.add_argument("--notebook-id", required=True)
    p_slides.add_argument(
        "--format",
        default="DETAILED_DECK",
        choices=["DETAILED_DECK", "PRESENTER_SLIDES"],
        dest="slide_format",
    )
    p_slides.add_argument("--instructions", default=None)
    p_slides.add_argument("--output-name", default="slides")

    # flashcards
    p_fc = sub.add_parser("flashcards", help="Generate flashcards")
    p_fc.add_argument("--notebook-id", required=True)
    p_fc.add_argument("--instructions", default=None)
    p_fc.add_argument("--output-name", default="flashcards")

    # report
    p_rpt = sub.add_parser("report", help="Generate a report")
    p_rpt.add_argument("--notebook-id", required=True)
    p_rpt.add_argument(
        "--format",
        default="BRIEFING_DOC",
        choices=["BRIEFING_DOC", "STUDY_GUIDE", "BLOG_POST", "CUSTOM"],
        dest="report_format",
    )
    p_rpt.add_argument("--custom-prompt", default=None)
    p_rpt.add_argument("--output-name", default="report")

    return parser


async def _async_main(args: argparse.Namespace) -> None:
    async with NotebookLMSkill() as nlm:
        if args.command == "create":
            nb = await nlm.create_notebook(args.title)
            print(json.dumps({"id": nb.id, "title": nb.title}))

        elif args.command == "list":
            notebooks = await nlm.list_notebooks()
            for nb in notebooks:
                print(f"{nb.id}  {nb.title}")

        elif args.command == "add-sources":
            urls: list[str] = list(args.urls or [])
            if args.urls_file:
                with open(args.urls_file) as f:
                    urls += [line.strip() for line in f if line.strip()]
            if not urls:
                print("No URLs provided.", file=sys.stderr)
                sys.exit(1)
            await nlm.add_youtube_urls(args.notebook_id, urls)

        elif args.command == "ask":
            answer = await nlm.ask(args.notebook_id, args.question)
            print(answer)

        elif args.command == "infographic":
            await nlm.generate_infographic(
                args.notebook_id,
                style=args.style,
                orientation=args.orientation,
                detail=args.detail,
                instructions=args.instructions,
                output_name=args.output_name,
            )

        elif args.command == "slides":
            await nlm.generate_slide_deck(
                args.notebook_id,
                slide_format=args.slide_format,
                instructions=args.instructions,
                output_name=args.output_name,
            )

        elif args.command == "flashcards":
            await nlm.generate_flashcards(
                args.notebook_id,
                instructions=args.instructions,
                output_name=args.output_name,
            )

        elif args.command == "report":
            await nlm.generate_report(
                args.notebook_id,
                report_format=args.report_format,
                custom_prompt=args.custom_prompt,
                output_name=args.output_name,
            )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
