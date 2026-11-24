import importlib.util
import json
from pathlib import Path
import struct
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


@pytest.mark.parametrize('short_avi_header', [False, True])
def test_end_to_end_september_three_mp4_no_original_change(tmp_path, short_avi_header):
    rate=16000
    signal=np.random.default_rng(11).integers(-20000,20000,size=rate*8,dtype=np.int16)
    root=tmp_path/'00_INBOX'; mom=root/'000003'/'delivery'/'CAM_A'/'mother1.avi'; child=root/'000003'/'delivery'/'CAM_B'/'children1.avi'
    make_avi(mom,signal,tmp_path)
    make_avi(child,signal[rate*2:],tmp_path)
    if short_avi_header:
        for path in (mom, child):
            # Reproduce an AVI writer counting PCM blocks instead of individual samples.
            data = bytearray(path.read_bytes())
            start = data.index(b'auds')
            assert data[start-8:start-4] == b'strh'
            length = struct.unpack_from('<I', data, start + 32)[0]
            struct.pack_into('<I', data, start + 32, length // 256)
            struct.pack_into('<I', data, start + 44, 0xffffffff)
            path.write_bytes(data)
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
    for role, seconds in (('mom', 8), ('child', 6)):
        media = report['input_media'][role]
        assert media['audio_seconds'] == seconds
        assert media['audio_timing']['samples'] == seconds * rate
        if short_avi_header:
            assert float(media['audio_timing']['header_seconds']) < 1
    assert (module.checksum(mom),module.checksum(child))==before
    assert sorted(p.suffix for p in dest.iterdir())==['.json','.mp4','.mp4','.mp4']
    assert all((dest/x['filename']).stat().st_size>0 for x in report['outputs'].values())
    with pytest.raises(module.SyncError, match='exists'):
        module.execute_job(jobs[0],target)
    assert not (root/'000003'/'delivery'/'synced').exists()


@pytest.mark.parametrize('second_pts,wav_samples,why', [
    (1792, 512, 'timestamps'), (1280, 512, 'timestamps'), (1536, 500, 'PCM duration'),
])
def test_avi_timing_rejects_inconsistent_evidence(tmp_path, monkeypatch, second_pts, wav_samples, why):
    def probe(cmd, *, stdout, **kwargs):
        stdout.write('frame|best_effort_timestamp=1280|nb_samples=256\n')
        stdout.write(f'frame|best_effort_timestamp={second_pts}|nb_samples=256\n')
        return subprocess.CompletedProcess(cmd, 0, stderr='')
    monkeypatch.setattr(subprocess, 'run', probe)
    pcm = tmp_path / 'sound.wav'
    write_wav(pcm, np.zeros(wav_samples))
    with pytest.raises(module.SyncError, match=why):
        module.avi_audio_timing('ffprobe', tmp_path/'input.avi',
                                dict(sample_rate=16000, time_base='1/16000'), pcm)


def test_avi_video_decode_failure_preserves_timing_without_candidate(tmp_path):
    audio = np.random.default_rng(32).integers(-15000, 15000, 16000 * 16, dtype=np.int16)
    mom, child = tmp_path/'mom.avi', tmp_path/'child.avi'
    make_avi(mom, audio, tmp_path)
    make_avi(child, audio[16000:], tmp_path)
    packets = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                       '-show_packets', '-show_entries', 'packet=pos,size',
                                       '-of', 'json', str(child)], text=True)
    damaged = json.loads(packets)['packets'][-20]
    with child.open('r+b') as fp:
        fp.seek(int(damaged['pos']))
        fp.write(b'\xaa' * int(damaged['size']))
    job = module.Job('999999', 'synthetic', 1, mom, child, 'explicit_user_pair')
    with pytest.raises(module.SyncError, match='encode failed'):
        module.execute_job(job, tmp_path/'out')
    report_path, = (tmp_path/'out').rglob('sync_report.json')
    report = json.loads(report_path.read_text())
    assert report['status'] == 'FAILED' and report['outputs'] == {}
    assert report['offset_seconds'] == pytest.approx(1) and report['common_seconds'] == pytest.approx(15)
    assert not list((tmp_path/'out').rglob('*.mp4'))
    assert not module.target_folder(tmp_path/'out', job).exists()


def test_output_identity_cannot_traverse(tmp_path):
    mom=tmp_path/'mom.avi'; child=tmp_path/'child.avi'
    mom.write_bytes(b'x'); child.write_bytes(b'y')
    for invalid in ['../escape', '000003/../../other', 'NOT_AN_ID']:
        job=module.Job(invalid,'reviewed',1,mom,child,'explicit_user_pair')
        with pytest.raises(module.SyncError, match='invalid participant'):
            module.target_folder(tmp_path/'out',job)
    with pytest.raises(module.SyncError):
        module.target_folder(tmp_path/'out', module.Job('000003','../escape',1,mom,child,'explicit_user_pair'))


@pytest.mark.parametrize('files', [
    ['CAM_A/mother1.avi', 'CAM_B/children1.avi', 'CAM_B/SNAP9999.avi'],
    ['mother1.avi', 'children1.avi', 'mother.avi'],
    ['take-1/CAM_A/mother1.avi', 'take-2/CAM_B/children1.avi'],
    ['CAM_A/toma_1/mother1.avi', 'CAM_B/toma_2/children1.avi'],
    ['CAM_A/mother1_take1.avi', 'CAM_B/children1_take2.avi'],
    ['visit-A/mother1.avi', 'visit-B/children1.avi'],
    ['visita-1/mother1.avi', 'visita-2/children1.avi'],
    ['2026-11-01/mother1.avi', '2026-11-02/children1.avi'],
    ['original/CAM_A/mother1.avi', 'repeat/CAM_B/children1.avi'],
    ['CAM_A/original/mother1.avi', 'CAM_B/repeat/children1.avi'],
    ['CAM_A/game-2/mother1.avi', 'CAM_B/game-2/children1.avi'],
])
def test_discovery_blocks_unresolved_identity_before_encoding(tmp_path, files, monkeypatch):
    root = tmp_path / 'source'
    session = root / '999999' / 'reviewed'
    for relative in files:
        path = session / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    def unexpected_encode(*args, **kwargs):
        pytest.fail('Ambiguous input reached execute_job')
    monkeypatch.setattr(module, 'execute_job', unexpected_encode)
    output = tmp_path / 'output'
    args = ['--source-root', str(root), '--participant', '999999', '--session-root', 'reviewed',
            '--game', '1', '--output-root', str(output)]
    assert module.main([*args, '--execute']) == 2
    assert not output.exists()


def test_tagged_pair_with_other_incomplete_game(tmp_path):
    root = tmp_path / 'source'
    session = root / '999999' / 'visit-A' / '2026-11-01'
    for name in ('CAM_A/2026-11-01/take-1/mother1.avi', 'CAM_B/take-1/children1.avi',
                 'CAM_A/take-1/mother2.avi'):
        path = session / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    jobs, issues = module.find_jobs(root, '999999', 'visit-A/2026-11-01')
    assert [job.game for job in jobs] == [1]
    assert any('game 2' in issue for issue in issues)


def prepared_pair(tmp_path, offset, sound):
    rate = 16000
    length = abs(offset) + 4
    rng = np.random.default_rng(191)
    if sound == 'periodic':
        unit = rng.integers(-14000, 14000, rate//4, dtype=np.int16)
        audio = np.tile(unit, int(length*4))
    elif sound == 'silent':
        audio = np.zeros(int(rate*length), dtype=np.int16)
    else:
        audio = rng.integers(-14000, 14000, size=int(rate*length), dtype=np.int16)
    paths = []
    for role, color, start in [('mom', 'red', max(0, -offset)), ('child', 'blue', max(0, offset))]:
        path = tmp_path / f'{role}_source.mp4'
        wav = tmp_path / f'{role}.wav'
        write_wav(wav, audio[int(start*rate):])
        subprocess.run(['ffmpeg','-nostdin','-v','error','-n','-f','lavfi','-i',
                        f'color={color}:s=96x64:r=8','-i',str(wav),'-t',str(length-start),
                        '-map','0:v:0','-map','1:a:0','-c:v','libx264','-c:a','aac',str(path)], check=True)
        paths.append(path)
    return paths


@pytest.mark.parametrize('offset,sound,reason', [
    (0.875, 'broadband', None), (-0.875, 'broadband', None),
    (31.25, 'broadband', 'OFFSET_EXCEEDS_REVIEW_LIMIT'),
    (0, 'periodic', 'COMPETING_FFT_PEAK'), (0, 'silent', 'INSUFFICIENT_ACTIVE_AUDIO'),
])
def test_reviewed_mp4_cli(tmp_path, capsys, offset, sound, reason):
    mom, child = prepared_pair(tmp_path, offset, sound)
    prefix = 'ID999999_V01_G02_T03'
    result = module.main(['--mom', str(mom), '--child', str(child), '--participant', '999999',
                          '--session-root', 'synthetic/take-03', '--game', '2', '--output-prefix', prefix,
                          '--output-root', str(tmp_path/'results'), '--execute'])
    summary = json.loads(capsys.readouterr().out)['results'][0]
    dest = Path(summary['output_folder'])
    report = json.loads((dest/'sync_report.json').read_text())
    assert report['qc_status'] == 'NotApproved'
    assert report['input_sha256'] == {'mom': module.checksum(mom), 'child': module.checksum(child)}
    if sound == 'broadband':
        assert report['offset_seconds'] == pytest.approx(offset, abs=1/16000)
    if reason:
        assert result == 2 and summary['status'] == 'NEEDS_REVIEW'
        assert reason in report['review_reasons']
        assert not report['trims'] and not report['outputs'] and not list(dest.glob('*.mp4'))
        return
    assert result == 0 and summary['status'] == 'CANDIDATE_FOR_MANUAL_QC'
    assert not report['review_reasons'] and report['common_seconds'] == pytest.approx(4)
    for role, output in report['outputs'].items():
        suffix = role if role == 'side_by_side' else role + '_synced'
        assert output['filename'] == f'{prefix}_{suffix}.mp4' and output['fully_decoded']
        assert output['sha256'] == module.checksum(dest/output['filename'])
        assert output['media']['video_seconds'] == pytest.approx(4, abs=1/8)
    side = dest/report['outputs']['side_by_side']['filename']
    pixels = subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(side),'-frames:v','1',
                                      '-vf','scale=64:32','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    left, right = np.frombuffer(pixels, dtype=np.uint8).reshape(32,64,3)[16,[16,48],:]
    assert left[0] > 200 and left[2] < 30 and right[2] > 200 and right[0] < 30


def test_review_limit_does_not_change_estimated_offset(tmp_path):
    mom, child = prepared_pair(tmp_path, 1.25, 'broadband')
    job = module.Job('999999', 'synthetic', 1, mom, child, 'explicit_user_pair')
    _, report = module.execute_job(job, tmp_path/'out', max_offset_seconds=1)
    assert report['offset_seconds'] == pytest.approx(1.25, abs=1/16000)
    assert report['review_reasons'] == ['OFFSET_EXCEEDS_REVIEW_LIMIT']
