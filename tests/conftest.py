import pytest


@pytest.fixture(autouse=True)
def isolated_application_data(tmp_path, monkeypatch):
    monkeypatch.setenv("SILING_CONFIG_DIR", str(tmp_path / "app-data"))
