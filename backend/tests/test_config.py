import pytest
from pydantic import ValidationError

from recallgraph.core.config import Settings


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECALLGRAPH_ENVIRONMENT", "staging")
    monkeypatch.setenv("RECALLGRAPH_JWT_SECRET", "s" * 40)
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


@pytest.mark.parametrize("secret", [None, "too-short"])
def test_deployed_environments_require_a_real_jwt_secret(
    monkeypatch: pytest.MonkeyPatch, secret: str | None
) -> None:
    monkeypatch.setenv("RECALLGRAPH_ENVIRONMENT", "production")
    if secret is not None:
        monkeypatch.setenv("RECALLGRAPH_JWT_SECRET", secret)

    with pytest.raises(ValidationError, match="RECALLGRAPH_JWT_SECRET"):
        Settings()
