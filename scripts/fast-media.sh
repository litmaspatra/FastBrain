#!/data/data/com.termux/files/usr/bin/bash
set -u

MODE="${1:-}"
[ "$#" -gt 0 ] && shift
QUERY="$*"

if [ -z "$MODE" ] || [ -z "$QUERY" ]; then
  echo 'Usage: fast-media simpmusic|ytmusic|youtube|youtube-latest "SEARCH QUERY"' >&2
  exit 2
fi

case "$MODE" in
  simpmusic)
    PACKAGE="com.maxrave.simpmusic"
    KIND="music"
    ;;
  ytmusic)
    PACKAGE="app.morphe.android.apps.youtube.music"
    KIND="music"
    ;;
  youtube)
    PACKAGE="app.morphe.android.youtube"
    KIND="video"
    ;;
  youtube-latest)
    PACKAGE="app.morphe.android.youtube"
    KIND="video"
    ;;
  *)
    echo "ERROR: unsupported media mode: $MODE" >&2
    exit 2
    ;;
esac

if [ "$MODE" = "youtube-latest" ]; then
  # ytsearchdate is not supported consistently across yt-dlp builds.
  # Fetch a small flat result set, then pick the newest dated result locally.
  SEARCH_JSON="$(timeout 8s yt-dlp \
    --flat-playlist \
    --dump-single-json \
    "ytsearch10:$QUERY" \
    --no-warnings 2>/dev/null || true)"

  VIDEO_ID="$(printf '%s' "$SEARCH_JSON" | python3.13 -c '
import json,sys
try:
    data=json.load(sys.stdin)
except Exception:
    raise SystemExit(0)
entries=data.get("entries") or []
def key(e):
    ts=e.get("timestamp") or e.get("release_timestamp") or 0
    if ts:
        return (1, float(ts))
    d=(e.get("upload_date") or e.get("release_date") or "").replace("-","")
    try: return (1, float(d))
    except Exception: return (0, 0)
dated=[e for e in entries if e and (e.get("timestamp") or e.get("release_timestamp") or e.get("upload_date") or e.get("release_date"))]
choice=max(dated,key=key) if dated else (entries[0] if entries else None)
if choice:
    print(choice.get("id") or "")
' 2>/dev/null)"
else
  VIDEO_ID="$(timeout 7s yt-dlp \
    --flat-playlist \
    --playlist-end 1 \
    --print '%(id)s' \
    "ytsearch1:$QUERY" \
    --no-warnings 2>/dev/null | head -n1)"
fi

if [ -z "$VIDEO_ID" ]; then
  echo 'ERROR: Fast media search returned no result.' >&2
  exit 3
fi

if [ "$KIND" = "music" ]; then
  URL="https://music.youtube.com/watch?v=$VIDEO_ID"
else
  URL="https://www.youtube.com/watch?v=$VIDEO_ID"
fi

if ! am start \
  -a android.intent.action.VIEW \
  -d "$URL" \
  -p "$PACKAGE" >/dev/null; then
  echo 'ERROR: Media launch failed.' >&2
  exit 4
fi

echo "Opening $MODE: $URL"
