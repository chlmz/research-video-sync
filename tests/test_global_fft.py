"""September NumPy formula as mathematical oracle; only generated PCM audio."""
from dataclasses import replace
import numpy as np
import pytest
from rg2019.config import SyncParams
from rg2019 import syncest as sync

RATE = 400
PRM = SyncParams(sample_rate=RATE, global_fft_enabled=True, window_seconds=10,
                 fine_search_seconds=1, max_lag_seconds=120)


def recordings(ms, cs, md, cd, seed=3):
    rng = np.random.default_rng(seed)
    wall = rng.integers(-12000,12000,size=int((max(ms+md,cs+cd)+1)*RATE),dtype=np.int16)
    return wall[int(ms*RATE):int((ms+md)*RATE)], wall[int(cs*RATE):int((cs+cd)*RATE)]


def september_numpy(a,b):
    # Exact historical NumPy mathematical operations (read_wav RMS normalization).
    a = (a.astype(float)/np.sqrt(np.mean(a.astype(float)**2))).astype(np.float32)
    b = (b.astype(float)/np.sqrt(np.mean(b.astype(float)**2))).astype(np.float32)
    n = len(a)+len(b)-1
    corr = np.fft.irfft(np.fft.rfft(a,n=n)*np.conj(np.fft.rfft(b,n=n)),n=n)
    k = int(np.argmax(corr))
    return (k-n if k>n//2 else k)/RATE


@pytest.mark.parametrize('ms,cs,md,cd', [(0,180,450,220),(180,0,220,450),(0,135.25,400,200),(135.25,0,200,400)])
def test_september_long_offsets_sign_and_trims(ms,cs,md,cd):
    a,b=recordings(ms,cs,md,cd)
    expected=cs-ms
    assert september_numpy(a,b) == pytest.approx(expected,abs=1/RATE)
    estimate=sync.estimate_offset(a,b,PRM)
    assert estimate.ok, estimate.reason
    assert estimate.offset_seconds == pytest.approx(expected,abs=.01)
    mt,ct=sync.trim_plan(estimate.offset_seconds)
    assert ms+mt == pytest.approx(cs+ct,abs=.01)
    assert estimate.n_agree >= 3
    assert all(y.position_seconds-x.position_seconds >= PRM.window_seconds for x,y in zip(estimate.windows,estimate.windows[1:]))


@pytest.mark.parametrize('reverse',[False,True])
def test_asymmetric_linear_lags_fix_historical_half_array_wrap(reverse):
    a,b=recordings(0,350,500,100)
    if reverse:a,b=b,a
    expected=-350 if reverse else 350
    assert abs(september_numpy(a,b)-expected)>100
    estimate=sync.estimate_offset(a,b,PRM)
    assert estimate.ok and estimate.offset_seconds == pytest.approx(expected,abs=.01)


def test_unrelated_and_silence_rejected():
    a,_=recordings(0,0,400,400,1)
    b,_=recordings(0,0,400,400,2)
    assert not sync.estimate_offset(a,b,PRM).ok
    assert not sync.estimate_offset(a,np.zeros_like(a),PRM).ok


def test_global_maximum_alone_cannot_authorize(monkeypatch):
    a,_=recordings(0,0,400,400,1)
    b,_=recordings(0,0,400,400,2)
    monkeypatch.setattr(sync,'_global_candidates',lambda *args:[dict(offset_seconds=180,ncc=1.)])
    result=sync.estimate_offset(a,b,PRM)
    assert not result.ok and result.offset_seconds is None


def test_repeated_content_multiple_validated_offsets_rejected():
    rng=np.random.default_rng(7)
    period=rng.integers(-10000,10000,80*RATE,dtype=np.int16)
    a=np.tile(period,6)
    result=sync.estimate_offset(a,a,PRM)
    assert not result.ok and 'ambiguous' in result.reason


def test_memory_budget_rejects_before_fft(monkeypatch):
    a,b=recordings(0,180,450,220)
    monkeypatch.setattr(sync,'fftconvolve',lambda *a,**k:pytest.fail('FFT allocated before admission'))
    result=sync.estimate_offset(a,b,replace(PRM,global_fft_memory_mb=1))
    assert not result.ok and 'memory budget' in result.reason


def test_mapped_inputs_unchanged_deterministic_and_container_times(tmp_path):
    a,b=recordings(0,180,450,220)
    paths=[tmp_path/'mom.pcm',tmp_path/'child.pcm']
    for p,x in zip(paths,[a,b]):x.tofile(p)
    before=[p.read_bytes() for p in paths]
    maps=[np.memmap(p,mode='r',dtype=np.int16) for p in paths]
    try:
        first=sync.estimate_offset(*maps,PRM,mom_audio_start=.25,child_audio_start=.75)
        second=sync.estimate_offset(*maps,PRM,mom_audio_start=.25,child_audio_start=.75)
        assert first.to_dict()==second.to_dict()
        assert first.ok and first.offset_seconds == pytest.approx(179.5,abs=.01)
        assert before==[p.read_bytes() for p in paths]
    finally:
        for x in maps:x._mmap.close()


def test_dc_gain_and_insufficient_overlap():
    a,b=recordings(0,180,450,220)
    a=(a.astype(float)*.5+5000).astype(np.int16)
    b=(b.astype(float)*.3-2000).astype(np.int16)
    assert sync.estimate_offset(a,b,PRM).ok
    a,b=recordings(0,380,400,100)
    assert not sync.estimate_offset(a,b,PRM).ok


def test_global_search_at_standard_analysis_sample_rate():
    rate=8000
    wall=np.random.default_rng(89).integers(-10000,10000,200*rate,dtype=np.int16)
    result=sync.estimate_offset(wall,wall[135*rate:195*rate],
        replace(PRM,sample_rate=rate,global_fft_memory_mb=1024))
    assert result.ok and result.offset_seconds == pytest.approx(135,abs=.002)
