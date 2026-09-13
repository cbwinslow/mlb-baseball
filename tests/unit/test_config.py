import pytest

from mlb_baseball import config


def test_toml_values_are_loaded_relative_to_the_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MLB_DOWNLOAD_DIR", raising=False)
    monkeypatch.delenv("MLB_ANALYTICS_WORKERS", raising=False)
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\ndownload_dir = 'artifacts'\nanalytics_workers = 4\n")

    settings = config.load_settings(path)

    assert settings.download_dir == (tmp_path / "artifacts").resolve()
    assert settings.analytics_workers == 4


def test_environment_overrides_toml_values(tmp_path, monkeypatch):
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\nanalytics_workers = 4\n")
    monkeypatch.setenv("MLB_ANALYTICS_WORKERS", "12")
    monkeypatch.setenv("MLB_DOWNLOAD_DIR", str(tmp_path / "environment-downloads"))

    settings = config.load_settings(path)

    assert settings.analytics_workers == 12
    assert settings.download_dir == (tmp_path / "environment-downloads").resolve()


def test_invalid_settings_fail_before_any_runtime_change(tmp_path):
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\nanalytics_workers = 25\n")

    with pytest.raises(config.ConfigError, match="analytics_workers"):
        config.load_settings(path)


def test_database_url_is_only_read_from_the_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        config.database_url()

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/mlb")
    assert config.database_url() == "postgresql://user:secret@localhost/mlb"


def test_unknown_toml_key_is_actionable(tmp_path):
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\nmade_up = true\n")

    with pytest.raises(config.ConfigError, match="unknown config setting"):
        config.load_settings(path)


def test_batch_memory_defaults_are_conservative(monkeypatch):
    # issue #202: the default must not be this project's own production
    # tuning (1GB/4GB) -- that would OOM a modest machine running this
    # project's code. Default to PostgreSQL's own conservative values.
    monkeypatch.delenv("MLB_BATCH_WORK_MEM", raising=False)
    monkeypatch.delenv("MLB_BATCH_MAINTENANCE_WORK_MEM", raising=False)

    settings = config.load_settings(None)

    assert settings.batch_work_mem == config.DEFAULT_BATCH_WORK_MEM == "4MB"
    assert (
        settings.batch_maintenance_work_mem == config.DEFAULT_BATCH_MAINTENANCE_WORK_MEM == "64MB"
    )


def test_batch_memory_settings_are_configurable_via_toml(tmp_path, monkeypatch):
    monkeypatch.delenv("MLB_BATCH_WORK_MEM", raising=False)
    monkeypatch.delenv("MLB_BATCH_MAINTENANCE_WORK_MEM", raising=False)
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\nbatch_work_mem = '1GB'\nbatch_maintenance_work_mem = '4GB'\n")

    settings = config.load_settings(path)

    assert settings.batch_work_mem == "1GB"
    assert settings.batch_maintenance_work_mem == "4GB"


def test_batch_memory_settings_are_overridable_via_env_var(tmp_path, monkeypatch):
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\nbatch_work_mem = '1GB'\n")
    monkeypatch.setenv("MLB_BATCH_WORK_MEM", "2GB")

    settings = config.load_settings(path)

    assert settings.batch_work_mem == "2GB"


def test_invalid_batch_memory_setting_is_rejected(tmp_path):
    path = tmp_path / "mlb.toml"
    path.write_text("[mlb]\nbatch_work_mem = 'DROP TABLE core.game; --'\n")

    with pytest.raises(config.ConfigError, match="batch_work_mem"):
        config.load_settings(path)
