# Changelog

## Reviewed headcam candidate

- The September adapter emits `LARGE_OFFSET_REVIEW` above the configured absolute offset and creates the three pending-QC MP4s when activity, FFT peak, common duration, stream timing and decode checks succeed.
- AVI timing uses timestamped decoded samples checked against the FFT PCM. Private scratch preparation can retain every valid H.264 packet and the complete audio when a single, proven terminal null packet prevents decoding.
- Synthetic coverage includes signed large offsets, competing peaks, overlap holds, erroneous AVI headers, terminal recovery, unsupported corruption and original preservation.
