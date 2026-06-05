from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("etf_rotation_config.yaml")


def load_rotation_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("rotation config must be a mapping")
    return payload


if __name__ == "__main__":
    load_rotation_config()
