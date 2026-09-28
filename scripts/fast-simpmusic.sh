#!/data/data/com.termux/files/usr/bin/bash
set -u

QUERY="$*"
if [ -z "$QUERY" ]; then
  echo 'Usage: fast-simpmusic "SEARCH QUERY"' >&2
  exit 2
fi

# Lightweight YouTube search: flat playlist avoids fetching full video metadata.
URL="$( (timeout 7s yt-dlp --flat-playlist --playlist-end 1 --print '%(url)s' "ytsearch1:$QUERY" 2>/dev/null || true) | head -n1 )"

if [ -z "$URL" ]; then
  echo 'ERROR: Fast music search returned no result.' >&2
  exit 3
fi

case "$URL" in
  http*) ;;
  *) URL="https://www.youtube.com/watch?v=$URL" ;;
esac

case "$URL" in
  https://www.youtube.com/watch?v=*)
    URL="${URL/https:\/\/www.youtube.com/https:\/\/music.youtube.com}"
    ;;
  https://youtube.com/watch?v=*)
    URL="${URL/https:\/\/youtube.com/https:\/\/music.youtube.com}"
    ;;
  https://youtu.be/*)
    VIDEO_ID="${URL##*/}"
    VIDEO_ID="${VIDEO_ID%%\?*}"
    URL="https://music.youtube.com/watch?v=$VIDEO_ID"
    ;;
esac

if ! am start -a android.intent.action.VIEW -d "$URL" -p com.maxrave.simpmusic >/dev/null; then
  echo 'ERROR: SimpMusic launch failed.' >&2
  exit 4
fi

echo "Opening in SimpMusic: $URL"
