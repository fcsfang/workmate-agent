import json
import zipfile

import pytest

from memory import DataPortabilityService


def test_data_portability_inventory_and_export_exclude_sensitive_runtime_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "records.json").write_text(json.dumps([{"user": "hello"}]), encoding="utf-8")
    (data_dir / "tasks.json").write_text("[]", encoding="utf-8")
    (data_dir / "knowledge").mkdir()
    (data_dir / "knowledge" / "USER.md").write_text("# User\n", encoding="utf-8")
    (data_dir / "screen_observations.json").write_text("[]", encoding="utf-8")
    (data_dir / "screenshots").mkdir()
    (data_dir / "screenshots" / "screen.jpg").write_bytes(b"private image")
    (data_dir / "chroma").mkdir()
    (data_dir / "chroma" / "chroma.sqlite3").write_bytes(b"index")
    (tmp_path / ".env").write_text("API_KEY=secret", encoding="utf-8")

    service = DataPortabilityService(data_dir)
    inventory = service.inventory()
    by_path = {item["path"]: item for item in inventory["files"]}

    assert by_path["records.json"]["exportable"] is True
    assert by_path["knowledge/USER.md"]["exportable"] is True
    assert by_path["knowledge/USER.md"]["category"] == "derived_profile"
    assert by_path["screen_observations.json"]["exportable"] is False
    assert by_path["screen_observations.json"]["sensitive"] is True
    assert by_path["screenshots/screen.jpg"]["exclusion_reason"] == "sensitive_binary"
    assert by_path["chroma/chroma.sqlite3"]["exclusion_reason"] == "rebuildable_index"

    result = service.export()
    export_path = service.resolve_export(result["filename"])
    with zipfile.ZipFile(export_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "data/records.json" in names
        assert "data/tasks.json" in names
        assert "data/knowledge/USER.md" in names
        assert "data/screen_observations.json" not in names
        assert "data/screenshots/screen.jpg" not in names
        assert "data/chroma/chroma.sqlite3" not in names
        assert ".env" not in names


def test_data_portability_rejects_export_path_traversal(tmp_path):
    service = DataPortabilityService(tmp_path / "data")
    with pytest.raises(ValueError, match="Invalid export filename"):
        service.resolve_export("../private.zip")
