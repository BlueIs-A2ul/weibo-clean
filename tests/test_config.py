from app.config import load_settings


def test_delays_env_override(monkeypatch):
    monkeypatch.setenv("WEIBO_MIN_DELAY", "0.5")
    monkeypatch.setenv("WEIBO_MAX_DELAY", "1.2")
    settings = load_settings()
    assert settings.request_min_delay == 0.5
    assert settings.request_max_delay == 1.2


def test_following_cache_ttl_default():
    assert load_settings().following_cache_ttl == 1800.0
