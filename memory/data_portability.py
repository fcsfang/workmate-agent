"""Inventory and export local Workmate runtime data without touching secrets."""

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class DataPortabilityService:
    """Expose a narrow, auditable boundary around local memory data."""

    GENERATED_DIRECTORIES = {"chroma"}
    SENSITIVE_DIRECTORIES = {"screenshots"}
    PORTABLE_SUFFIXES = {".json", ".md"}

    def __init__(self, data_dir: Path, export_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir).resolve()
        self.export_dir = Path(export_dir or (self.data_dir.parent / "archive" / "exports")).resolve()

    def inventory(self) -> Dict[str, Any]:
        files = self._inventory_files()
        exportable = [item for item in files if item["exportable"]]
        sensitive = [item for item in files if item["sensitive"]]
        return {
            "data_root": str(self.data_dir),
            "file_count": len(files),
            "total_bytes": sum(item["size_bytes"] for item in files),
            "exportable_file_count": len(exportable),
            "exportable_bytes": sum(item["size_bytes"] for item in exportable),
            "sensitive_file_count": len(sensitive),
            "files": files,
            "export_policy": {
                "included": ["JSON runtime state and Markdown long-term knowledge files"],
                "excluded": ["API keys and .env files", "screen screenshots", "rebuildable ChromaDB index", "cache and metadata files"],
            },
        }

    def export(self) -> Dict[str, Any]:
        inventory = self.inventory()
        exportable = [item for item in inventory["files"] if item["exportable"]]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        filename = f"workmate-memory-export-{timestamp}.zip"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        destination = self.export_dir / filename
        temporary = destination.with_suffix(".tmp")

        manifest = {
            "format": "workmate-memory-export",
            "format_version": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "file_count": len(exportable),
            "total_bytes": sum(item["size_bytes"] for item in exportable),
            "files": [
                {
                    "path": item["path"],
                    "size_bytes": item["size_bytes"],
                    "modified_at": item["modified_at"],
                    "category": item["category"],
                }
                for item in exportable
            ],
            "excluded": inventory["export_policy"]["excluded"],
        }

        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                for item in exportable:
                    source = self._safe_data_file(item["path"])
                    archive.write(source, arcname=f"data/{item['path']}")
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()

        return {
            "filename": filename,
            "created_at": manifest["created_at"],
            "file_count": manifest["file_count"],
            "total_bytes": manifest["total_bytes"],
            "download_url": f"/api/privacy/exports/{filename}",
            "excluded": manifest["excluded"],
        }

    def resolve_export(self, filename: str) -> Path:
        if not filename or Path(filename).name != filename or not filename.endswith(".zip"):
            raise ValueError("Invalid export filename")
        candidate = (self.export_dir / filename).resolve()
        if candidate.parent != self.export_dir or not candidate.is_file():
            raise ValueError("Export file not found")
        return candidate

    def _inventory_files(self) -> List[Dict[str, Any]]:
        if not self.data_dir.exists():
            return []
        files = []
        for path in sorted(self.data_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.data_dir)
            parts = set(relative.parts)
            generated = bool(parts & self.GENERATED_DIRECTORIES)
            sensitive = bool(parts & self.SENSITIVE_DIRECTORIES) or relative.name == "screen_observations.json"
            portable = path.suffix.lower() in self.PORTABLE_SUFFIXES and not generated and not sensitive
            stat = path.stat()
            files.append({
                "path": relative.as_posix(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "category": self._category(relative),
                "exportable": portable,
                "sensitive": sensitive,
                "exclusion_reason": self._exclusion_reason(relative, portable, generated, sensitive),
            })
        return files

    def _safe_data_file(self, relative_path: str) -> Path:
        candidate = (self.data_dir / relative_path).resolve()
        try:
            candidate.relative_to(self.data_dir)
        except ValueError as exc:
            raise ValueError("Export source escaped memory data directory") from exc
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError(f"Export source is unavailable: {relative_path}")
        return candidate

    @staticmethod
    def _category(relative: Path) -> str:
        if "screenshots" in relative.parts or relative.name == "screen_observations.json":
            return "screen_observation"
        if "daily_summaries" in relative.parts:
            return "summary"
        if "knowledge" in relative.parts and relative.suffix.lower() == ".md":
            return "derived_profile"
        if relative.name in {"records.json", "semantic_dialogues.json", "supervision_messages.json"}:
            return "conversation"
        if relative.name in {"tasks.json", "task_events.json", "task_state.json", "commitments.json", "focus_sessions.json"}:
            return "execution_state"
        if relative.name in {"user_profile.json", "behavior_patterns.json", "high_level_insights.json", "reflections.json"}:
            return "derived_profile"
        if relative.name.startswith("memory_") or relative.name == "retrieval_index.json" or "chroma" in relative.parts:
            return "memory_index"
        if relative.name.startswith("supervision_"):
            return "supervision"
        return "runtime_metadata"

    @staticmethod
    def _exclusion_reason(relative: Path, portable: bool, generated: bool, sensitive: bool) -> str:
        if portable:
            return ""
        if generated:
            return "rebuildable_index"
        if "screenshots" in relative.parts:
            return "sensitive_binary"
        if sensitive:
            return "sensitive_data"
        if relative.suffix.lower() not in DataPortabilityService.PORTABLE_SUFFIXES:
            return "non_portable_runtime_file"
        return "not_exportable"
