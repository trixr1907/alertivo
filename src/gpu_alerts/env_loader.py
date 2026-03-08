from __future__ import annotations

import os
import re
from pathlib import Path


ENV_LINE = re.compile(r"^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


def parse_powershell_value(value: str) -> str:
    parsed = value.strip()
    if (parsed.startswith('"') and parsed.endswith('"')) or (parsed.startswith("'") and parsed.endswith("'")):
        parsed = parsed[1:-1]
    return parsed


def load_powershell_env(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        match = ENV_LINE.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        os.environ[key] = parse_powershell_value(raw_value)
