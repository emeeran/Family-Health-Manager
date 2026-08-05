"""Production-mode config validation: required secrets must be set.

Mirrors the runtime guard in ``Settings.model_post_init`` — production refuses
to boot without ``HEALTH_CHECK_SECRET`` and ``ENCRYPTION_KEY``, so a misconfigured
deploy fails loud at startup instead of silently degrading security.
"""

import importlib

import pytest


def _fresh_settings(monkeypatch, **env):
    """Build a Settings instance from a clean env (bypassing the lru_cache)."""
    from app.core import config

    # Clear module-level state so each test starts fresh — including the
    # ENCRYPTION_KEY conftest sets for the rest of the suite, so a test that
    # omits it truly exercises the "missing key" path.
    for var in ("APP_ENV", "ENCRYPTION_KEY", "HEALTH_CHECK_SECRET", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(config)
    return config.Settings()


def test_prod_requires_encryption_key(monkeypatch):
    """Production without ENCRYPTION_KEY raises (dual-key mandate)."""
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        _fresh_settings(
            monkeypatch,
            APP_ENV="production",
            SECRET_KEY="a" * 48,
            HEALTH_CHECK_SECRET="hc-secret",
            # ENCRYPTION_KEY intentionally omitted
        )


def test_prod_requires_health_check_secret(monkeypatch):
    with pytest.raises(ValueError, match="HEALTH_CHECK_SECRET"):
        _fresh_settings(
            monkeypatch,
            APP_ENV="production",
            SECRET_KEY="a" * 48,
            ENCRYPTION_KEY="b" * 44,
        )


def test_prod_boots_with_both_secrets(monkeypatch):
    """Both secrets set → production constructs cleanly with DEBUG forced off."""
    s = _fresh_settings(
        monkeypatch,
        APP_ENV="production",
        SECRET_KEY="a" * 48,
        ENCRYPTION_KEY="b" * 44,
        HEALTH_CHECK_SECRET="hc-secret",
    )
    assert s.APP_ENV == "production"
    assert s.DEBUG is False


def test_dev_allows_missing_encryption_key(monkeypatch):
    """Dev mode keeps the legacy fallback (no hard requirement)."""
    s = _fresh_settings(
        monkeypatch,
        APP_ENV="development",
        SECRET_KEY="a" * 48,
    )
    assert s.ENCRYPTION_KEY == ""
