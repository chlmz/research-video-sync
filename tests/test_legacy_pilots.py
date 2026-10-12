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
