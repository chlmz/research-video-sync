#!/bin/bash

# ============================================================
#  sync_videos.sh — Audio-based Video Sync Tool
#  
#  Syncs two videos by matching their audio, then exports:
#    - camera1_synced.mp4
#    - camera2_synced.mp4
#    - side_by_side.mp4
#
#  Usage (Cowork will run this):
#    bash sync_videos.sh /path/to/video1.mp4 /path/to/video2.mp4
#
#  Or manually:
#    bash sync_videos.sh video1.mp4 video2.mp4
# ============================================================

set -e

# ---- Helpers ----
notify() {
    osascript -e "display dialog \"$1\" with title \"Video Sync\" buttons {\"OK\"} default button \"OK\"" 2>/dev/null || echo "$1"
}

notify_error() {
    osascript -e "display dialog \"$1\" with title \"Video Sync\" buttons {\"OK\"} default button \"OK\" with icon stop" 2>/dev/null || echo "ERROR: $1"
}

# ---- Check dependencies ----
for cmd in ffmpeg python3; do
    if ! command -v "$cmd" &>/dev/null; then
        notify_error "$cmd is not installed. Please install it first.\n\nFor ffmpeg: brew install ffmpeg\nFor python3: brew install python3"
        exit 1
    fi
done

# ---- Arguments ----
if [[ $# -lt 2 ]]; then
    notify_error "Please provide exactly 2 video files.\n\nUsage: bash sync_videos.sh video1.mp4 video2.mp4"
    exit 1
fi

VIDEO1="$1"
VIDEO2="$2"

if [[ ! -f "$VIDEO1" ]]; then notify_error "File not found: $VIDEO1"; exit 1; fi
if [[ ! -f "$VIDEO2" ]]; then notify_error "File not found: $VIDEO2"; exit 1; fi

# ---- Output folder (same as video1) ----
OUTDIR=$(dirname "$VIDEO1")
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTDIR="$OUTDIR/synced_$TIMESTAMP"
mkdir -p "$OUTDIR"

echo "📁 Output folder: $OUTDIR"
echo "🎬 Video 1: $VIDEO1"
echo "🎬 Video 2: $VIDEO2"
echo ""
echo "⏳ Step 1/4: Extracting audio tracks..."

# ---- Extract mono WAV audio for analysis ----
TMP=$(mktemp -d)
ffmpeg -i "$VIDEO1" -vn -ac 1 -ar 16000 -f wav "$TMP/audio1.wav" -loglevel error
ffmpeg -i "$VIDEO2" -vn -ac 1 -ar 16000 -f wav "$TMP/audio2.wav" -loglevel error

echo "✅ Audio extracted."
echo "⏳ Step 2/4: Analyzing audio to find sync offset..."

# ---- Python cross-correlation to find offset ----
OFFSET=$(python3 - "$TMP/audio1.wav" "$TMP/audio2.wav" <<'PYEOF'
import sys, struct, wave, math

def read_wav_samples(path):
    with wave.open(path, 'rb') as w:
        n = w.getnframes()
        raw = w.readframes(n)
        sampwidth = w.getsampwidth()
        nch = w.getnchannels()
        rate = w.getframerate()
        if sampwidth == 2:
            samples = struct.unpack(f'<{n*nch}h', raw)
        elif sampwidth == 4:
            samples = struct.unpack(f'<{n*nch}i', raw)
        else:
            samples = [b - 128 for b in raw]
        if nch > 1:
            samples = samples[::nch]
        total = math.sqrt(sum(s*s for s in samples) / len(samples)) or 1
        samples = [s / total for s in samples]
        return samples, rate

def cross_correlate_offset(a, b, rate, max_offset_sec=30):
    max_lag = int(rate * max_offset_sec)
    # Use shorter window for speed (first 60s)
    window = int(rate * 60)
    a = a[:window]
    b = b[:window]
    best_corr = -1
    best_lag = 0
    step = max(1, rate // 100)  # ~10ms resolution
    for lag in range(-max_lag, max_lag, step):
        if lag >= 0:
            sa = a[lag:lag+window//2]
            sb = b[:window//2]
        else:
            sa = a[:window//2]
            sb = b[-lag:-lag+window//2]
        n = min(len(sa), len(sb))
        if n < rate:
            continue
        corr = sum(x*y for x,y in zip(sa[:n], sb[:n])) / n
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_lag / rate

a, rate = read_wav_samples(sys.argv[1])
b, rate2 = read_wav_samples(sys.argv[2])
offset = cross_correlate_offset(a, b, rate)
# positive = video2 starts later (trim video2 start)
# negative = video1 starts later (trim video1 start)
print(f"{offset:.4f}")
PYEOF
)

echo "✅ Offset found: ${OFFSET}s"
echo "   (positive = Camera 2 starts later; negative = Camera 1 starts later)"
echo ""
echo "⏳ Step 3/4: Exporting synced individual videos..."

# ---- Apply offset and trim ----
# We trim whichever starts "later" so both begin at the same audio moment
NAME1=$(basename "${VIDEO1%.*}")
NAME2=$(basename "${VIDEO2%.*}")

OUT1="$OUTDIR/${NAME1}_synced.mp4"
OUT2="$OUTDIR/${NAME2}_synced.mp4"
OUT_SBS="$OUTDIR/side_by_side.mp4"

OFFSET_FLOAT=$(python3 -c "print(float('$OFFSET'))")

python3 - "$OFFSET_FLOAT" "$VIDEO1" "$VIDEO2" "$OUT1" "$OUT2" <<'PYEOF'
import sys, subprocess

offset = float(sys.argv[1])
v1, v2, out1, out2 = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

common_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "22",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]

if offset >= 0:
    # video2 audio starts later by `offset` seconds — skip start of video2
    subprocess.run(["ffmpeg", "-i", v1, *common_args, out1, "-loglevel", "error"], check=True)
    subprocess.run(["ffmpeg", "-ss", str(offset), "-i", v2, *common_args, out2, "-loglevel", "error"], check=True)
else:
    # video1 audio starts later — skip start of video1
    skip = str(abs(offset))
    subprocess.run(["ffmpeg", "-ss", skip, "-i", v1, *common_args, out1, "-loglevel", "error"], check=True)
    subprocess.run(["ffmpeg", "-i", v2, *common_args, out2, "-loglevel", "error"], check=True)
PYEOF

echo "✅ Synced videos exported."
echo "⏳ Step 4/4: Creating side-by-side video..."

# ---- Side-by-side: scale both to same height, stack horizontally ----
ffmpeg \
    -i "$OUT1" \
    -i "$OUT2" \
    -filter_complex \
        "[0:v]scale=-2:720[left];[1:v]scale=-2:720[right];[left][right]hstack=inputs=2[v];[0:a][1:a]amix=inputs=2:duration=shortest[a]" \
    -map "[v]" -map "[a]" \
    -c:v libx264 -preset fast -crf 22 \
    -c:a aac -b:a 192k \
    -movflags +faststart \
    "$OUT_SBS" \
    -loglevel error

echo ""
echo "✅ All done!"
echo ""
echo "📂 Output files in: $OUTDIR"
echo "   • ${NAME1}_synced.mp4"
echo "   • ${NAME2}_synced.mp4"
echo "   • side_by_side.mp4"

# ---- Cleanup ----
rm -rf "$TMP"

# ---- Mac notification ----
notify "✅ Sync complete!\n\nOffset applied: ${OFFSET}s\n\nFiles saved in:\n$OUTDIR\n\n• ${NAME1}_synced.mp4\n• ${NAME2}_synced.mp4\n• side_by_side.mp4"
