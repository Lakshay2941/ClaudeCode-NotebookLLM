"""
YouTube Research Skill
----------------------
Scrapes YouTube metadata (title, views, author, duration, URL) for a
given search query using yt-dlp — no API key required.

CLI usage:
    python skills/yt_research.py --query "AI agents 2025" --count 25
    python skills/yt_research.py --query "AI agents 2025" --count 25 --json

Programmatic usage:
    from skills.yt_research import search_youtube
    results = search_youtube("AI agents 2025", count=25)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

import yt_dlp


@dataclass
class VideoResult:
    rank: int
    title: str
    url: str
    author: str
    views: int | None
    duration_seconds: int | None
    duration_str: str
    upload_date: str | None
    thumbnail: str | None

    def display(self) -> str:
        views_str = f"{self.views:,}" if self.views is not None else "N/A"
        return (
            f"[{self.rank:>2}] {self.title}\n"
            f"     Author : {self.author}\n"
            f"     Views  : {views_str}\n"
            f"     Length : {self.duration_str}\n"
            f"     Date   : {self.upload_date or 'N/A'}\n"
            f"     URL    : {self.url}"
        )


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "N/A"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_entry(rank: int, info: dict[str, Any]) -> VideoResult:
    video_id = info.get("id", "")
    url = info.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
    duration = info.get("duration")
    if isinstance(duration, float):
        duration = int(duration)
    return VideoResult(
        rank=rank,
        title=info.get("title", "Unknown Title"),
        url=url,
        author=info.get("uploader") or info.get("channel") or "Unknown",
        views=info.get("view_count"),
        duration_seconds=duration,
        duration_str=_format_duration(duration),
        upload_date=info.get("upload_date"),
        thumbnail=info.get("thumbnail"),
    )


def search_youtube(
    query: str,
    count: int = 25,
    no_check_certificate: bool = False,
) -> list[VideoResult]:
    """Search YouTube and return video metadata without downloading anything.

    Args:
        query: The search term.
        count: Maximum number of results to return (default 25).
        no_check_certificate: Skip SSL cert verification (useful behind proxies).

    Returns:
        List of VideoResult objects ordered by YouTube's relevance/trending rank.
    """
    search_url = f"ytsearch{count}:{query}"

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
        "nocheckcertificate": no_check_certificate,
        # Fetch enough extra metadata even in flat mode
        "extractor_args": {"youtube": {"player_skip": ["configs", "webpage"]}},
    }

    results: list[VideoResult] = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_url, download=False)

    if not info or "entries" not in info:
        return results

    for rank, entry in enumerate(info["entries"], start=1):
        if entry is None:
            continue
        results.append(_build_entry(rank, entry))
        if len(results) >= count:
            break

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search YouTube and print video metadata."
    )
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument(
        "--count", "-n", type=int, default=25, help="Number of results (default 25)"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", dest="as_json", help="Output as JSON"
    )
    parser.add_argument(
        "--output", "-o", help="Write results to this file (JSON format)"
    )
    parser.add_argument(
        "--no-check-certificate",
        action="store_true",
        dest="no_check_certificate",
        help="Skip SSL certificate verification (useful behind corporate proxies)",
    )
    args = parser.parse_args()

    print(f"Searching YouTube for: {args.query!r} (top {args.count})\n", file=sys.stderr)

    videos = search_youtube(args.query, args.count, args.no_check_certificate)

    if not videos:
        print("No results found.", file=sys.stderr)
        sys.exit(1)

    if args.as_json or args.output:
        data = [asdict(v) for v in videos]
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(payload)
            print(f"Results saved to {args.output}", file=sys.stderr)
        if args.as_json:
            print(payload)
    else:
        for v in videos:
            print(v.display())
            print()


if __name__ == "__main__":
    main()
