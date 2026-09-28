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
    SEARCH="ytsearch1"
    KIND="music"
    ;;
  ytmusic)
    PACKAGE="app.morphe.android.apps.youtube.music"
    SEARCH="ytsearch1"
    KIND="music"
    ;;
  youtube)
    PACKAGE="app.morphe.android.youtube"
    SEARCH="ytsearch1"
    KIND="video"
    ;;
  youtube-latest)
    PACKAGE="app.morphe.android.youtube"
    SEARCH="ytsearchdate1"
    KIND="video"
    ;;
  *)
    echo "ERROR: unsupported media mode: $MODE" >&2
    exit 2
    ;;
esac

VIDEO_ID="$(timeout 7s yt-dlp \
  --flat-playlist \
  --playlist-end 1 \
  --print '%(id)s' \
  "$SEARCH:$QUERY" \
  --no-warnings 2>/dev/null | head -n1)"

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
