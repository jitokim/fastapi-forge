from fastapi_forge.logging import get_logging_config


def test_get_logging_config_respects_log_level_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    config = get_logging_config()

    assert config["handlers"]["root_stdout"]["level"] == "DEBUG"
    assert config["handlers"]["gunicorn_stdout"]["level"] == "DEBUG"
    assert config["root"]["level"] == "DEBUG"
