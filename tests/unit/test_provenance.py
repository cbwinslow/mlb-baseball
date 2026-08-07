from mlb_baseball.model.provenance import artifact_sha256


def test_artifact_sha256_is_content_addressed(tmp_path):
    artifact = tmp_path / "model.json"
    artifact.write_text('{"model": 1}')

    first = artifact_sha256(artifact)
    second = artifact_sha256(artifact)

    assert first == second
    assert len(first) == 64
