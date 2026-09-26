import pytest
from pydantic import ValidationError

from recallgraph.core.config import Settings


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECALLGRAPH_ENVIRONMENT", "staging")
    monkeypatch.setenv("RECALLGRAPH_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("RECALLGRAPH_LOG_JSON", "false")

    settings = Settings()

    assert (settings.environment, settings.log_level, settings.log_json) == (
        "staging",
        "DEBUG",
        False,
    )


def test_invalid_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECALLGRAPH_ENVIRONMENT", "prod-typo")

    with pytest.raises(ValidationError):
        Settings()
