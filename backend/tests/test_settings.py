def test_admin_setting_overrides_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LOVKTV_DATA", str(tmp_path))
    monkeypatch.setenv("LOVKTV_POINTS", "1")
    from lovktv.storage import settings, store

    store.DB_PATH = tmp_path / "settings.sqlite"
    store.MEDIA_DIR = tmp_path / "media"
    store.init_db()
    assert settings.get("points_enabled") is True
    settings.set_value("points_enabled", False)
    assert settings.get("points_enabled") is False
    assert next(item for item in settings.catalog() if item["key"] == "points_enabled")["source"] == "admin"
