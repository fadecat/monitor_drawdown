import os
from pathlib import Path
from typing import Dict, Optional


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_wrapping_quotes(value.strip())
    return values


def load_local_env(path: str = ".env.local") -> Dict[str, str]:
    return parse_env_file(Path(path))


def get_env_value(name: str, local_env: Optional[Dict[str, str]] = None, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None:
        return value.strip()
    if local_env is None:
        return default
    return str(local_env.get(name, default)).strip()
