import shutil
from pathlib import Path

from tools import sync_legacy_pilots as legacy


def test_detect_role_historical_variants():
    mom_names = [
        "mom.mp4",
        "momview.mp4",
        "mother cam.avi",
        "mothe_cam.avi",
        "mum.mov",
        "parentview.mp4",
        "Mother Romi 1.AVI",
    ]
    child_names = [
        "child.mp4",
        "childview.mp4",
        "children.avi",
        "chil_cam.avi",
        "chid.mp4",
        "cildview.mp4",
        "Son Gael 1.AVI",
    ]
    for name in mom_names:
        assert legacy.detect_role(Path(name)) == "mom", name
    for name in child_names:
        assert legacy.detect_role(Path(name)) == "child", name


def test_detect_role_does_not_guess_unlabelled_snap():
    assert legacy.detect_role(Path("SNAP0009.AVI")) is None


def test_detect_role_ambiguous():
    assert legacy.detect_role(Path("mom_child.mp4")) == "ambiguous"


def test_participant_id_families_and_zero_padding():
    assert legacy.participant_id_from_component("ID 100392").display == "ID100392"
    assert legacy.participant_id_from_component("IDS004").key == "ids:4"
    assert legacy.participant_id_from_component("IDPiloto001").key == "idpiloto:1"
    assert legacy.participant_id_from_component("IDpiloto0001").key == "idpiloto:1"
    assert legacy.participant_id_from_component("IDRomi001").key == "idromi:1"
    assert legacy.participant_id_from_component("COD0001") is None


def test_discovery_uses_folder_id_and_ignores_derived_subfolders(tmp_path):
    root = tmp_path / "00_SOURCE_LEGACY"
    participant = root / "piloto" / "ID 100392"
    participant.mkdir(parents=True)

    mom = participant / "mother_cam.AVI"
    child = participant / "chid_cam.AVI"
    mom.write_bytes(b"x")
    child.write_bytes(b"x")

    converted = participant / "mp4"
    converted.mkdir()
    (converted / "mother_cam.mp4").write_bytes(b"x")
    (converted / "child_cam.mp4").write_bytes(b"x")

    cases = legacy.discover_cases(root)
    case = cases["id:100392"]
    assert case.pid.display == "ID100392"
    assert case.mom == [mom]
    assert case.child == [child]


def test_existing_historical_sync_is_detected_across_zero_padding(tmp_path):
    root = tmp_path / "00_SOURCE_LEGACY"

    raw = root / "Piloto fase 1" / "Video crus" / "IDPiloto001"
    raw.mkdir(parents=True)
    (raw / "mother cam.AVI").write_bytes(b"x")
    (raw / "child cam.AVI").write_bytes(b"x")

    synced = root / "Piloto fase 1" / "videos sync" / "IDpiloto0001"
    synced.mkdir(parents=True)
    (synced / "IDPiloto001motherview.mp4").write_bytes(b"x")
    (synced / "IDPiloto001childview.mp4").write_bytes(b"x")

    assert "idpiloto:1" in legacy.find_existing_synced_ids(root)


def test_side_by_side_files_are_not_raw_candidates(tmp_path):
    root = tmp_path / "00_SOURCE_LEGACY"
    participant = root / "Prepiloto" / "IDS004"
    participant.mkdir(parents=True)
    (participant / "IDS004brinde.mp4").write_bytes(b"x")
    (participant / "IDS004_mom.mp4").write_bytes(b"x")
    (participant / "IDS004_child.mp4").write_bytes(b"x")

    case = legacy.discover_cases(root)["ids:4"]
    assert len(case.mom) == 1
    assert len(case.child) == 1
    assert not case.unclassified


# ---------------------------------------------------------------------------
# find_existing_synced_pairs (new)
# ---------------------------------------------------------------------------

def test_find_existing_synced_pairs_returns_clear_pair(tmp_path):
    """Sync folder with one mom + one child → is_clear, exact paths returned."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "Piloto" / "videos sync" / "IDPiloto001"
    synced.mkdir(parents=True)
    mom = synced / "IDPiloto001motherview.mp4"
    child = synced / "IDPiloto001childview.mp4"
    mom.write_bytes(b"x")
    child.write_bytes(b"x")

    pairs = legacy.find_existing_synced_pairs(root)
    assert "idpiloto:1" in pairs
    pair = pairs["idpiloto:1"]
    assert pair.is_clear
    assert pair.mom == [mom]
    assert pair.child == [child]


def test_find_existing_synced_pairs_detects_unclassified_sync_files(tmp_path):
    """Sync folder with SNAP files that can't be role-classified → not is_clear."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "ID100336" / "video sincro"
    synced.mkdir(parents=True)
    snap1 = synced / "SNAP00083.mp4"
    snap2 = synced / "SNAP0016.mp4"
    snap1.write_bytes(b"x")
    snap2.write_bytes(b"x")

    pairs = legacy.find_existing_synced_pairs(root)
    assert "id:100336" in pairs
    pair = pairs["id:100336"]
    assert not pair.is_clear
    assert len(pair.unclassified) == 2
    assert "id:100336" not in legacy.find_existing_synced_ids(root)


def test_find_existing_synced_pairs_ambiguous_filename_in_sync_folder(tmp_path):
    """A file matching both mom and child patterns in a sync folder → not is_clear."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "ID100392" / "sincronizado"
    synced.mkdir(parents=True)
    (synced / "mothercam_childcam.mp4").write_bytes(b"x")  # ambiguous role (both patterns)
    (synced / "child.mp4").write_bytes(b"x")

    pairs = legacy.find_existing_synced_pairs(root)
    pair = pairs["id:100392"]
    assert not pair.is_clear
    assert len(pair.ambiguous) == 1


def test_find_existing_synced_ids_backward_compat(tmp_path):
    """find_existing_synced_ids still returns the set of clear-pair keys."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "Piloto" / "videos sync" / "IDPiloto001"
    synced.mkdir(parents=True)
    (synced / "IDPiloto001motherview.mp4").write_bytes(b"x")
    (synced / "IDPiloto001childview.mp4").write_bytes(b"x")

    uncl = root / "ID100336" / "sincronizado"
    uncl.mkdir(parents=True)
    (uncl / "SNAP00083.mp4").write_bytes(b"x")
    (uncl / "SNAP0016.mp4").write_bytes(b"x")

    ids = legacy.find_existing_synced_ids(root)
    assert "idpiloto:1" in ids
    assert "id:100336" not in ids


# ---------------------------------------------------------------------------
# dry-run status reporting (no ffmpeg required)
# ---------------------------------------------------------------------------

def test_dry_run_reports_would_import_existing_sync(tmp_path, capsys):
    """Clear historical pair → WOULD_IMPORT_EXISTING_SYNC in dry-run output."""
    source = tmp_path / "00_SOURCE_LEGACY"
    output = tmp_path / "01_CURATED"
    output.mkdir(parents=True)

    synced_dir = source / "videos sync" / "IDPiloto001"
    synced_dir.mkdir(parents=True)
    (synced_dir / "IDPiloto001motherview.mp4").write_bytes(b"fake")
    (synced_dir / "IDPiloto001childview.mp4").write_bytes(b"fake")

    raw_dir = source / "IDPiloto001"
    raw_dir.mkdir(parents=True)
    (raw_dir / "mother_cam.AVI").write_bytes(b"fake")
    (raw_dir / "child_cam.AVI").write_bytes(b"fake")

    rc = legacy.main([
        "--dry-run",
        "--source-root", str(source),
        "--output-root", str(output),
    ])
    out = capsys.readouterr().out
    assert "WOULD_IMPORT_EXISTING_SYNC" in out
    assert "SKIP_LEGACY_SYNC_EXISTS" not in out
    assert rc == 0


def test_dry_run_reports_review_synced_ambiguous_for_unclassifiable_sync_files(tmp_path, capsys):
    """Unclassifiable sync-folder files → REVIEW_SYNCED_AMBIGUOUS."""
    source = tmp_path / "00_SOURCE_LEGACY"
    output = tmp_path / "01_CURATED"
    output.mkdir(parents=True)

    synced_dir = source / "ID100336" / "video sincro"
    synced_dir.mkdir(parents=True)
    (synced_dir / "SNAP00083.mp4").write_bytes(b"fake")
    (synced_dir / "SNAP0016.mp4").write_bytes(b"fake")

    rc = legacy.main([
        "--dry-run",
        "--source-root", str(source),
        "--output-root", str(output),
    ])
    out = capsys.readouterr().out
    assert "REVIEW_SYNCED_AMBIGUOUS" in out
    assert rc == 2


def test_already_complete_when_all_three_curated_outputs_exist(tmp_path, capsys):
    """ALREADY_COMPLETE when the curated folder already has all three valid outputs."""
    source = tmp_path / "00_SOURCE_LEGACY"
    output = tmp_path / "01_CURATED"

    synced_dir = source / "videos sync" / "IDPiloto001"
    synced_dir.mkdir(parents=True)
    (synced_dir / "IDPiloto001motherview.mp4").write_bytes(b"fake")
    (synced_dir / "IDPiloto001childview.mp4").write_bytes(b"fake")

    out_pid = output / "IDPiloto001"
    out_pid.mkdir(parents=True)
    for name in ("IDPiloto001_mom_synced.mp4", "IDPiloto001_child_synced.mp4",
                 "IDPiloto001_side_by_side.mp4"):
        (out_pid / name).write_bytes(b"output")

    rc = legacy.main([
        "--dry-run",
        "--source-root", str(source),
        "--output-root", str(output),
    ])
    out = capsys.readouterr().out
    assert "ALREADY_COMPLETE" in out
    assert "SKIP_OUTPUT_COMPLETE" not in out
    assert rc == 0


def test_import_existing_sync_creates_curated_outputs(tmp_path, video_cache):
    """Real import: historical synced pair → curated outputs + new side-by-side."""
    source = tmp_path / "00_SOURCE_LEGACY"
    output = tmp_path / "01_CURATED"

    vid_dir = video_cache(0.0, 0.0)

    synced_dir = source / "videos sync" / "ID100392"
    synced_dir.mkdir(parents=True)
    shutil.copy2(vid_dir / "mom.mp4", synced_dir / "ID100392motherview.mp4")
    shutil.copy2(vid_dir / "child.mp4", synced_dir / "ID100392childview.mp4")

    rc = legacy.main([
        "--source-root", str(source),
        "--output-root", str(output),
    ])

    out_pid = output / "ID100392"
    assert (out_pid / "ID100392_mom_synced.mp4").is_file()
    assert (out_pid / "ID100392_child_synced.mp4").is_file()
    assert (out_pid / "ID100392_side_by_side.mp4").is_file()
    assert rc == 0


def test_import_existing_sync_is_idempotent(tmp_path, video_cache):
    """Running twice with a clear historical pair → ALREADY_COMPLETE on second run."""
    source = tmp_path / "00_SOURCE_LEGACY"
    output = tmp_path / "01_CURATED"

    vid_dir = video_cache(0.0, 0.0)
    synced_dir = source / "videos sync" / "ID100392"
    synced_dir.mkdir(parents=True)
    shutil.copy2(vid_dir / "mom.mp4", synced_dir / "ID100392motherview.mp4")
    shutil.copy2(vid_dir / "child.mp4", synced_dir / "ID100392childview.mp4")

    legacy.main(["--source-root", str(source), "--output-root", str(output)])

    rc = legacy.main([
        "--dry-run",
        "--source-root", str(source),
        "--output-root", str(output),
    ])
    assert rc == 0


def test_dry_run_reports_would_add_side_by_side_when_pair_exists_without_sbs(tmp_path, capsys):
    """WOULD_ADD_SIDE_BY_SIDE when curated mom+child exist but side-by-side is missing."""
    source = tmp_path / "00_SOURCE_LEGACY"
    source.mkdir(parents=True)
    output = tmp_path / "01_CURATED"

    out_pid = output / "ID100024"
    out_pid.mkdir(parents=True)
    (out_pid / "ID100024_mom_synced.mp4").write_bytes(b"existing-mom")
    (out_pid / "ID100024_child_synced.mp4").write_bytes(b"existing-child")

    rc = legacy.main([
        "--dry-run",
        "--source-root", str(source),
        "--output-root", str(output),
    ])
    out = capsys.readouterr().out
    assert "WOULD_ADD_SIDE_BY_SIDE" in out
    assert "REVIEW_OUTPUT_CONFLICT" not in out
    assert rc == 0


def test_add_side_by_side_creates_sbs_from_existing_curated_pair(tmp_path, video_cache):
    """ADD_SIDE_BY_SIDE: creates side-by-side from existing curated mom+child, leaves them intact."""
    source = tmp_path / "00_SOURCE_LEGACY"
    source.mkdir(parents=True)
    output = tmp_path / "01_CURATED"

    vid_dir = video_cache(0.0, 0.0)
    out_pid = output / "ID100024"
    out_pid.mkdir(parents=True)
    shutil.copy2(vid_dir / "mom.mp4", out_pid / "ID100024_mom_synced.mp4")
    shutil.copy2(vid_dir / "child.mp4", out_pid / "ID100024_child_synced.mp4")

    rc = legacy.main([
        "--source-root", str(source),
        "--output-root", str(output),
    ])

    assert (out_pid / "ID100024_mom_synced.mp4").is_file()
    assert (out_pid / "ID100024_child_synced.mp4").is_file()
    assert (out_pid / "ID100024_side_by_side.mp4").is_file()
    assert rc == 0


# ---------------------------------------------------------------------------
# ExistingSyncedPair.is_clear — relaxed logic (spec §1–3)
# ---------------------------------------------------------------------------

def test_clear_pair_with_brinde_extra_is_clear(tmp_path):
    """mom + child + brinde/combined derivative → is_clear; derivative tracked separately."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "IDPiloto006" / "videos sync"
    synced.mkdir(parents=True)
    (synced / "IDPiloto0006_momview.mp4").write_bytes(b"x")
    (synced / "IDPiloto0006_childview.mp4").write_bytes(b"x")
    (synced / "videobrinde.mp4").write_bytes(b"x")

    pairs = legacy.find_existing_synced_pairs(root)
    pair = pairs["idpiloto:6"]
    assert pair.is_clear
    assert len(pair.mom) == 1
    assert len(pair.child) == 1
    assert len(pair.derivative) == 1
    assert pair.derivative[0].name == "videobrinde.mp4"
    assert not pair.unclassified


def test_clear_pair_with_unclassified_extras_is_still_clear(tmp_path):
    """mom + child + truly-unclassified extras → is_clear; unclassified tracked but not blocking."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "IDPiloto005" / "videos sync"
    synced.mkdir(parents=True)
    (synced / "IDpiloto0005_momview.mp4").write_bytes(b"x")
    (synced / "IDpiloto0005_childview.mp4").write_bytes(b"x")
    (synced / "rafa_liz.mp4").write_bytes(b"x")
    (synced / "rafa_liz_clip.mp4").write_bytes(b"x")

    pairs = legacy.find_existing_synced_pairs(root)
    pair = pairs["idpiloto:5"]
    assert pair.is_clear
    assert len(pair.mom) == 1
    assert len(pair.child) == 1
    assert len(pair.unclassified) == 2


def test_two_moms_not_clear(tmp_path):
    """Two mom files + one child → not is_clear."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "ID100392" / "sincronizado"
    synced.mkdir(parents=True)
    (synced / "motherview_cam1.mp4").write_bytes(b"x")
    (synced / "motherview_cam2.mp4").write_bytes(b"x")
    (synced / "child.mp4").write_bytes(b"x")

    pair = legacy.find_existing_synced_pairs(root)["id:100392"]
    assert not pair.is_clear
    assert len(pair.mom) == 2


def test_two_children_not_clear(tmp_path):
    """One mom + two child files → not is_clear."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "ID100392" / "sincronizado"
    synced.mkdir(parents=True)
    (synced / "mom.mp4").write_bytes(b"x")
    (synced / "child1.mp4").write_bytes(b"x")
    (synced / "child2.mp4").write_bytes(b"x")

    pair = legacy.find_existing_synced_pairs(root)["id:100392"]
    assert not pair.is_clear
    assert len(pair.child) == 2


def test_ambiguous_role_file_not_clear(tmp_path):
    """A file matching both mom+child patterns in a sync folder → not is_clear (ambiguous)."""
    root = tmp_path / "00_SOURCE_LEGACY"
    synced = root / "ID100392" / "sincronizado"
    synced.mkdir(parents=True)
    (synced / "mom.mp4").write_bytes(b"x")
    (synced / "child.mp4").write_bytes(b"x")
    (synced / "mothercam_childcam.mp4").write_bytes(b"x")

    pair = legacy.find_existing_synced_pairs(root)["id:100392"]
    assert not pair.is_clear
    assert len(pair.ambiguous) == 1


def test_probe_video_pair_raises_duration_mismatch(tmp_path, monkeypatch):
    """probe_video_pair raises DurationMismatch when durations differ materially."""
    from rg2019.media import MediaInfo
    from tools.sync_legacy_pilots import (
        probe_video_pair, DurationMismatch, load_config,
        SYNCED_PAIR_DURATION_TOLERANCE_SECONDS,
    )
    import rg2019.media as _media

    cfg = load_config(None, None, None)
    mom_path = tmp_path / "mom.mp4"
    child_path = tmp_path / "child.mp4"
    mom_path.write_bytes(b"fake")
    child_path.write_bytes(b"fake")

    durations = {mom_path.name: 100.0, child_path.name: 100.0 + SYNCED_PAIR_DURATION_TOLERANCE_SECONDS + 1.0}

    def _fake_probe(cfg, path):
        d = durations[path.name]
        return MediaInfo(
            size_bytes=4, duration=d, format_name="mp4", format_start=0.0,
            video_codec="h264", audio_codec="aac", audio_rate=44100, audio_channels=2,
        )

    monkeypatch.setattr(_media, "probe", _fake_probe)

    import pytest
    with pytest.raises(DurationMismatch):
        probe_video_pair(cfg, mom_path, child_path)


def test_dry_run_would_import_existing_sync_for_pair_with_extras(tmp_path, capsys):
    """Clear pair with brinde derivative → WOULD_IMPORT_EXISTING_SYNC; derivative tracked in pair."""
    source = tmp_path / "00_SOURCE_LEGACY"
    output = tmp_path / "01_CURATED"
    output.mkdir(parents=True)

    synced = source / "IDPiloto006" / "videos sync"
    synced.mkdir(parents=True)
    (synced / "IDPiloto0006_momview.mp4").write_bytes(b"fake")
    (synced / "IDPiloto0006_childview.mp4").write_bytes(b"fake")
    (synced / "videobrinde.mp4").write_bytes(b"fake")

    rc = legacy.main([
        "--dry-run",
        "--source-root", str(source),
        "--output-root", str(output),
    ])
    assert "WOULD_IMPORT_EXISTING_SYNC" in capsys.readouterr().out
    assert rc == 0

    # The pair is classified correctly: clear, with the brinde file in derivative.
    pair = legacy.find_existing_synced_pairs(source)["idpiloto:6"]
    assert pair.is_clear
    assert len(pair.derivative) == 1
    assert pair.derivative[0].name == "videobrinde.mp4"
