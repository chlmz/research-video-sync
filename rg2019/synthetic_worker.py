"""Internal disposable process. Reuses the unchanged scientific implementation."""
import json
from pathlib import Path
import sys

from .config import load
from . import media, syncest


def work(attempt):
    cfg = load(attempt / 'config.json')
    paths = {r: attempt / (r + '.avi') for r in ('mom', 'child')}
    infos = {r: media.probe(cfg, p) for r, p in paths.items()}
    for info in infos.values():
        if not (info.has_video and info.has_audio and info.duration and 0 < info.duration <= 120):
            raise ValueError('invalid source or synthetic duration limit exceeded')
    arrays = {}
    try:
        for role, path in paths.items():
            arrays[role] = media.extract_audio(cfg, path, attempt / (role + '.pcm'), cfg.sync.sample_rate)
        estimate = syncest.estimate_offset(arrays['mom'], arrays['child'], cfg.sync,
                                          infos['mom'].audio_start, infos['child'].audio_start)
    finally:
        for array in arrays.values():
            array._mmap.close()
    if not estimate.ok:
        raise ValueError('LOW_CONFIDENCE: ' + estimate.reason)
    outputs = attempt / 'outputs'
    outputs.mkdir()
    trims = syncest.trim_plan(estimate.offset_seconds, cfg.encode.min_trim_seconds)
    for (role, src), trim in zip(paths.items(), trims):
        dst = outputs / (role + '.mp4')
        media.encode(cfg, src, dst, trim, infos[role])
        actual = media.probe(cfg, dst)
        if not (actual.has_audio and actual.has_video and actual.duration and actual.duration > 0
                and abs(actual.duration - (infos[role].duration - trim)) <= cfg.encode.duration_tolerance_seconds):
            raise ValueError('technical output validation failed')
    (outputs / 'sync.json').write_text(json.dumps(estimate.to_dict()), encoding='utf-8')


if __name__ == '__main__':
    work(Path(sys.argv[1]))
