#!/data/data/com.termux/files/usr/bin/python3.13
from __future__ import annotations

import re
import shutil
import subprocess
import sys

MORPHE_PKG = "app.morphe.android.apps.youtube.music"


def to_music_url(url: str) -> str:
    url = url.strip()
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    if m:
        return f"https://music.youtube.com/watch?v={m.group(1)}"
    return url


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: fast-music.py SEARCH QUERY", file=sys.stderr)
        return 2
    query = " ".join(sys.argv[1:]).strip()
    yt = shutil.which("yt-dlp")
    am = shutil.which("am")
    if not yt or not am:
        print("missing yt-dlp or am", file=sys.stderr)
        return 3

    cmd = [
        yt,
        "--socket-timeout", "3",
        "--retries", "0",
        "--extractor-retries", "0",
        "--playlist-items", "1",
        "--print", "%(webpage_url)s",
        f"ytsearch1:{query}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
    except subprocess.TimeoutExpired:
        print("music search timed out", file=sys.stderr)
        return 4
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout).strip(), file=sys.stderr)
        return proc.returncode or 5

    url = ""
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("http"):
            url = line
            break
    if not url:
        print("no result", file=sys.stderr)
        return 6

    url = to_music_url(url)
    launch = subprocess.run([
        am,
        "start",
        "-a", "android.intent.action.VIEW",
        "-d", url,
        "-p", MORPHE_PKG,
    ], capture_output=True, text=True, timeout=3)
    if launch.returncode != 0:
        print((launch.stderr or launch.stdout).strip(), file=sys.stderr)
        return launch.returncode or 7

    print(f"Opening in Morphe: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
