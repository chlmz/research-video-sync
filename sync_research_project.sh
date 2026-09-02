#!/bin/bash

# ============================================================
#  sync_research_project.sh
#  Mother-Child Interaction Research — Batch Video Sync
#
#  - Scans a project folder for participant subfolders
#  - Detects new (unprocessed) participants
#  - Syncs by audio using FFT cross-correlation (numpy)
#  - Exports: ID_mom_synced.mp4, ID_child_synced.mp4,
#             ID_side_by_side.mp4, and sync_report.csv
#
#  Usage:
#    bash sync_research_project.sh /path/to/videos_projectname
# ============================================================

set -e

# ---- Config ----
MOM_PATTERN="_mom"
CHILD_PATTERN="_child"
SYNCED_MARKER=".sync_done"
REPORT_NAME="sync_report.csv"

# ---- Helpers ----
notify() {
    osascript -e "display dialog \"$1\" with title \"Research Sync\" buttons {\"OK\"} default button \"OK\"" 2>/dev/null || echo "$1"
}

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# ---- Check dependencies ----
for cmd in ffmpeg python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is not installed. Run: brew install ffmpeg python3"
        exit 1
    fi
done

# ---- Install numpy if missing ----
python3 -c "import numpy" 2>/dev/null || {
    log "Installing numpy (one time only)..."
    pip3 install numpy --quiet --break-system-packages 2>/dev/null || \
    pip3 install numpy --quiet 2>/dev/null || true
}

# ---- Argument: project folder ----
PROJECT_DIR="${1:-}"
if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR" ]]; then
    echo "ERROR: Please provide a valid project folder."
    echo "Usage: bash sync_research_project.sh /path/to/project_folder"
    exit 1
fi

PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)
REPORT_FILE="$PROJECT_DIR/$REPORT_NAME"
log "📁 Project folder: $PROJECT_DIR"

# ---- Init report ----
if [[ ! -f "$REPORT_FILE" ]]; then
    echo "participant_id,mom_file,child_file,offset_seconds,status,processed_at,output_folder" > "$REPORT_FILE"
fi

# ---- Scan participant folders ----
PROCESSED=0
SKIPPED=0
FAILED=0
NEWLY_DONE=()

for PART_DIR in "$PROJECT_DIR"/*/; do
    [[ -d "$PART_DIR" ]] || continue

    PART_ID=$(basename "$PART_DIR")

    # Skip if already synced
    if [[ -f "$PART_DIR/$SYNCED_MARKER" ]]; then
        log "⏭️  $PART_ID — already synced, skipping."
        ((SKIPPED++))
        continue
    fi

    log "🔍 $PART_ID — scanning..."

    # Find mom and child videos (any format)
    MOM_FILE=$(find "$PART_DIR" -maxdepth 1 \( -iname "*${MOM_PATTERN}*.mp4" -o -iname "*${MOM_PATTERN}*.avi" -o -iname "*${MOM_PATTERN}*.mov" -o -iname "*${MOM_PATTERN}*.mkv" \) | head -1)
    CHILD_FILE=$(find "$PART_DIR" -maxdepth 1 \( -iname "*${CHILD_PATTERN}*.mp4" -o -iname "*${CHILD_PATTERN}*.avi" -o -iname "*${CHILD_PATTERN}*.mov" -o -iname "*${CHILD_PATTERN}*.mkv" \) | head -1)

    if [[ -z "$MOM_FILE" || -z "$CHILD_FILE" ]]; then
        log "⚠️  $PART_ID — could not find both mom/child videos. Skipping."
        echo "$PART_ID,,,missing_files,$(date '+%Y-%m-%d %H:%M:%S')," >> "$REPORT_FILE"
        ((FAILED++))
        continue
    fi

    log "   Mom:   $(basename "$MOM_FILE")"
    log "   Child: $(basename "$CHILD_FILE")"

    # ---- Output folder ----
    OUT_DIR="$PART_DIR/synced"
    mkdir -p "$OUT_DIR"

    # ---- Extract mono 16kHz WAV for analysis ----
    TMP=$(mktemp -d)
    log "   Extracting audio..."
    ffmpeg -i "$MOM_FILE"   -vn -ac 1 -ar 16000 -f wav "$TMP/mom.wav"   -loglevel error
    ffmpeg -i "$CHILD_FILE" -vn -ac 1 -ar 16000 -f wav "$TMP/child.wav" -loglevel error

    # ---- FFT-based cross-correlation for accurate offset ----
    log "   Calculating sync offset (FFT method)..."
    OFFSET=$(python3 - "$TMP/mom.wav" "$TMP/child.wav" <<'PYEOF'
import sys, wave, struct, math

def read_wav(path):
    with wave.open(path, 'rb') as w:
        n = w.getnframes()
        raw = w.readframes(n)
        sw = w.getsampwidth()
        nch = w.getnchannels()
        rate = w.getframerate()
        if sw == 2:
            samples = list(struct.unpack(f'<{n*nch}h', raw))
        elif sw == 4:
            samples = list(struct.unpack(f'<{n*nch}i', raw))
        else:
            samples = [b - 128 for b in raw]
        if nch > 1:
            samples = samples[::nch]
        rms = math.sqrt(sum(s*s for s in samples) / len(samples)) or 1
        return [s / rms for s in samples], rate

try:
    import numpy as np

    a_raw, rate = read_wav(sys.argv[1])
    b_raw, _    = read_wav(sys.argv[2])
    a = np.array(a_raw, dtype=np.float32)
    b = np.array(b_raw, dtype=np.float32)

    # FFT cross-correlation — uses full signal for maximum accuracy
    n = len(a) + len(b) - 1
    FA = np.fft.rfft(a, n=n)
    FB = np.fft.rfft(b, n=n)
    corr = np.fft.irfft(FA * np.conj(FB), n=n)

    lag = int(np.argmax(corr))
    if lag > n // 2:
        lag -= n

    print(f"{lag / rate:.4f}")

except ImportError:
    # Fallback: pure Python with wide search window
    a, rate = read_wav(sys.argv[1])
    b, _    = read_wav(sys.argv[2])
    max_lag = int(rate * 120)
    seg = int(rate * 30)
    mid = len(a) // 3
    seg_a = a[mid:mid + seg]
    best, best_lag = -float('inf'), 0
    step = max(1, rate // 50)
    for lag in range(-max_lag, max_lag, step):
        if lag >= 0:
            sb = b[lag:lag + seg]
            sa = seg_a
        else:
            sb = b[mid:mid + seg]
            sa = a[mid - lag:mid - lag + seg]
        n = min(len(sa), len(sb))
        if n < rate: continue
        corr = sum(x * y for x, y in zip(sa[:n], sb[:n])) / n
        if corr > best:
            best, best_lag = corr, lag
    print(f"{best_lag / rate:.4f}")
PYEOF
)

    log "   Offset: ${OFFSET}s (positive = child started later; negative = mom started later)"

    # ---- Export synced videos ----
    OUT_MOM="$OUT_DIR/${PART_ID}_mom_synced.mp4"
    OUT_CHILD="$OUT_DIR/${PART_ID}_child_synced.mp4"
    OUT_SBS="$OUT_DIR/${PART_ID}_side_by_side.mp4"

    log "   Exporting synced videos..."
    python3 - "$OFFSET" "$MOM_FILE" "$CHILD_FILE" "$OUT_MOM" "$OUT_CHILD" <<'PYEOF'
import sys, subprocess
offset = float(sys.argv[1])
mom, child, out_mom, out_child = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

# Use -ss AFTER -i for frame-accurate trimming (slower but precise)
enc = ["-c:v","libx264","-preset","fast","-crf","22",
       "-c:a","aac","-b:a","192k","-movflags","+faststart"]

trim = str(abs(offset))

if offset > 0:
    # Mom started earlier — trim mom's start by offset
    subprocess.run(["ffmpeg","-y","-i",mom,"-ss",trim,*enc,out_mom,"-loglevel","error"],check=True)
    subprocess.run(["ffmpeg","-y","-i",child,*enc,out_child,"-loglevel","error"],check=True)
else:
    # Child started earlier — trim child's start by offset
    subprocess.run(["ffmpeg","-y","-i",mom,*enc,out_mom,"-loglevel","error"],check=True)
    subprocess.run(["ffmpeg","-y","-i",child,"-ss",trim,*enc,out_child,"-loglevel","error"],check=True)
PYEOF

    # ---- Side-by-side ----
    log "   Creating side-by-side..."
    ffmpeg -y \
        -i "$OUT_MOM" -i "$OUT_CHILD" \
        -filter_complex \
          "[0:v]scale=-2:720,setpts=PTS-STARTPTS[left];[1:v]scale=-2:720,setpts=PTS-STARTPTS[right];[left][right]hstack=inputs=2[v];[0:a][1:a]amix=inputs=2:duration=shortest[a]" \
        -map "[v]" -map "[a]" \
        -c:v libx264 -preset fast -crf 22 \
        -c:a aac -b:a 192k \
        -movflags +faststart \
        "$OUT_SBS" -loglevel error

    # ---- Mark as done ----
    touch "$PART_DIR/$SYNCED_MARKER"

    # ---- Append to report ----
    echo "$PART_ID,$(basename "$MOM_FILE"),$(basename "$CHILD_FILE"),$OFFSET,success,$(date '+%Y-%m-%d %H:%M:%S'),$OUT_DIR" >> "$REPORT_FILE"

    NEWLY_DONE+=("$PART_ID")
    ((PROCESSED++))
    rm -rf "$TMP"
    log "   ✅ $PART_ID done."
done

# ---- Summary ----
echo ""
log "════════════════════════════════"
log "✅ Newly synced:  $PROCESSED participant(s)"
log "⏭️  Skipped:       $SKIPPED (already done)"
log "⚠️  Failed/missing: $FAILED"
log "📄 Report: $REPORT_FILE"
log "════════════════════════════════"

if [[ ${#NEWLY_DONE[@]} -gt 0 ]]; then
    DONE_LIST=$(printf "• %s\n" "${NEWLY_DONE[@]}")
    notify "✅ Sync complete!\n\nProcessed (${PROCESSED}):\n${DONE_LIST}\n\nSkipped: ${SKIPPED}\nFailed: ${FAILED}\n\nReport: $REPORT_FILE"
else
    notify "ℹ️ No new participants.\n\nSkipped (already done): ${SKIPPED}\nFailed/missing: ${FAILED}"
fi
