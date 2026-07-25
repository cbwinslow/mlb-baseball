from pathlib import Path
from unittest.mock import patch

from mlb_baseball.connectors import retrosheet


def test_download_year_calls_manifest_with_expected_url_and_filename():
    fake_path = Path("/tmp/fake/2025csvs.zip")
    with patch.object(retrosheet.manifest, "download", return_value=fake_path) as mock_download:
        result = retrosheet._download_year(2025)

    assert result is fake_path
    mock_download.assert_called_once_with(
        "retrosheet",
        "2025csvs.zip",
        "https://www.retrosheet.org/downloads/2025/2025csvs.zip",
    )


def test_download_year_returns_none_when_manifest_download_returns_none():
    with patch.object(retrosheet.manifest, "download", return_value=None):
        assert retrosheet._download_year(2099) is None
