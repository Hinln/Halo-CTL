from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


def load_dotenv(path: str | None = None) -> Dict[str, str]:
    p = Path(path or ".env")
    if not p.exists() or not p.is_file():
        return {}

    out: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        if k not in os.environ:
            os.environ[k] = v
        out[k] = v
    return out

