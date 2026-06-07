"""Runtime data paths for Workmate Agent memory files."""

from pathlib import Path


MEMORY_PACKAGE_DIR = Path(__file__).resolve().parent
MEMORY_DATA_DIR = MEMORY_PACKAGE_DIR / "data"


def memory_data_path(name: str) -> Path:
    return MEMORY_DATA_DIR / name
