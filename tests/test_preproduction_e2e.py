from examples.preproduction_demo import demonstrate


def test_three_layouts_real_generated_media_and_recovery(tmp_path):
    result = demonstrate(tmp_path / 'CÂMERAS synthetic')
    assert len(result['publications']) == 3
    assert len(result['blocked']) == 2
    assert all(j['game'] is None for j in result['blocked'])
    assert result['originals_unchanged'] and result['recovered']
    assert result['qc_status'] == 'NotApproved'
    assert result['real_smb_validated'] is False
