import importlib.util
import json
from pathlib import Path
import subprocess
import wave

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'sync_september_field.py'
spec = importlib.util.spec_from_file_location('sync_september_field', SCRIPT)
import sys
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def write_wav(path, signal, rate=16000):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(signal, dtype='<i2').tobytes())


@pytest.mark.parametrize('start_mom,start_child,mom_len,child_len', [
    (0, 2, 10, 7), (2, 0, 7, 10), (0, 0, 8, 8), (0, 6, 14, 6), (6, 0, 6, 14),
    (0, 20, 30, 4), (20, 0, 4, 30)
])
def test_september_fft_correct_sign_and_asymmetric_lags(tmp_path, start_mom, start_child, mom_len, child_len):
    rate = 400  # arithmetic valid at any sample rate
    source = np.random.default_rng(123).integers(-19000, 19000, size=24000, dtype=np.int16)
    a = source[int(start_mom*rate):int((start_mom+mom_len)*rate)]
    b = source[int(start_child*rate):int((start_child+child_len)*rate)]
    write_wav(tmp_path/'mom.wav', a, rate)
    write_wav(tmp_path/'child.wav', b, rate)
    report = module.september_offset(tmp_path/'mom.wav', tmp_path/'child.wav')
    assert abs(report['offset_seconds']-(start_child-start_mom)) < .01


def test_nested_folder_game_pairing_and_auxiliaries(tmp_path):
    root = tmp_path/'00_INBOX'
    session = root/'000003'/'delivery'/'session-A'
    files = [session/'CAM_A'/'DCIM'/'nested'/'mother1.AVI',
             session/'CAM_B'/'DCIM'/'children1.avi',
             session/'CAM_A'/'DCIM'/'mother2.avi',
             session/'CAM_B'/'DCIM'/'children2.AVI']
    for p in files:
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(b'avi-dummy')
    (session/'CAM_A'/'DCIM'/'movie.insv').write_bytes(b'auxiliary')
    jobs,issues=module.find_jobs(root,'000003','delivery/session-A')
    assert not issues
    assert sorted(j.game for j in jobs)==[1,2]
    assert all(j.selection=='explicit_game' for j in jobs)
    assert 'mother1' in jobs[0].mom.name
    assert 'children1' in jobs[0].child.name


def test_single_unnumbered_pair_requires_reviewed_session(tmp_path):
    root = tmp_path/'00_INBOX'; session=root/'000001'/'session-X'
    (session/'CAM_A').mkdir(parents=True)
    (session/'CAM_B').mkdir()
    (session/'CAM_A'/'mother.avi').write_bytes(b'x')
    (session/'CAM_B'/'children.avi').write_bytes(b'y')
    jobs,issues=module.find_jobs(root,'000001','session-X')
    assert len(jobs)==1 and jobs[0].game==1 and jobs[0].selection=='reviewed_single_unnumbered'
    assert not issues
    (session/'CAM_B'/'children2.avi').write_bytes(b'z')
    jobs,issues=module.find_jobs(root,'000001','session-X')
    assert len(jobs)==0 and issues


def test_duplicate_and_transfer_and_source_output_collision(tmp_path):
    root = tmp_path/'00_INBOX'; session=root/'000001'/'s'
    (session/'m'/'mother1.avi').parent.mkdir(parents=True)
    (session/'m'/'mother1.avi').write_bytes(b'a')
    (session/'c').mkdir()
    (session/'c'/'children1.avi').write_bytes(b'b')
    (session/'c'/'backup-children1.avi').write_bytes(b'b')
    jobs,issues=module.find_jobs(root,'000001','s')
    assert not jobs and any('one mother and one child' in w for w in issues)
    (session/'c'/'backup-children1.avi').unlink()
    (session/'c'/'upload.partial').write_bytes(b'c')
    jobs,issues=module.find_jobs(root,'000001','s')
    assert not jobs and any('transfer in progress' in w for w in issues)
    (session/'c'/'upload.partial').unlink()
    module.outside_input(tmp_path/'result', [session/'m'/'mother1.avi'], root)
    with pytest.raises(module.SyncError):
        module.outside_input(root/'000001'/'results', [session/'m'/'mother1.avi'], root)


def make_avi(path: Path, audio: np.ndarray, tmp_path, rate=16000):
    raw = tmp_path/f'{path.stem}.raw'
    audio.tofile(raw)
    path.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','color=c=blue:s=160x120:r=10',
        '-f','s16le','-ar',str(rate),'-ac','1','-i',str(raw),'-shortest',
        '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','pcm_s16le','-f','avi',str(path)],check=True)


def test_end_to_end_september_three_mp4_no_original_change(tmp_path):
    rate=16000
    signal=np.random.default_rng(11).integers(-20000,20000,size=rate*8,dtype=np.int16)
    root=tmp_path/'00_INBOX'; mom=root/'000003'/'delivery'/'CAM_A'/'mother1.avi'; child=root/'000003'/'delivery'/'CAM_B'/'children1.avi'
    make_avi(mom,signal,tmp_path)
    make_avi(child,signal[rate*2:],tmp_path)
    before=(module.checksum(mom), module.checksum(child))
    jobs,issues=module.find_jobs(root,'000003','delivery')
    assert len(jobs)==1 and not issues
    target=tmp_path/'OUTPUT'
    dest,report=module.execute_job(jobs[0],target)
    assert report['offset_seconds']==pytest.approx(2.0,abs=0.01)
    assert report['qc_status']=='NotApproved'
    assert report['status']=='CANDIDATE_FOR_MANUAL_QC'
    assert report['trims']['mom']==pytest.approx(2.0,abs=.01)
    assert report['trims']['child']==0
    assert (module.checksum(mom),module.checksum(child))==before
    assert sorted(p.suffix for p in dest.iterdir())==['.json','.mp4','.mp4','.mp4']
    assert all((dest/x['filename']).stat().st_size>0 for x in report['outputs'].values())
    with pytest.raises(module.SyncError, match='exists'):
        module.execute_job(jobs[0],target)
    assert not (root/'000003'/'delivery'/'synced').exists()
