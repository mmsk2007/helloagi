from __future__ import annotations

from pathlib import Path
import os


def load_local_env(path: str = ".env") -> dict[str, str]:
    """Load a local .env file into process env without overriding existing vars."""
    p = Path(path)
    loaded: dict[str, str] = {}
    if not p.exists():
        return loaded

    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def save_env_values(values: dict[str, str], path: str = ".env"):
    """Persist selected env vars to a local .env file with best-effort private perms."""
    p = Path(path)
    existing_lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    updates = {k: v for k, v in values.items() if v}
    if not updates:
        return

    seen: set[str] = set()
    rendered: list[str] = []
    for raw_line in existing_lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            rendered.append(raw_line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rendered.append(raw_line)

    if rendered and rendered[-1].strip():
        rendered.append("")
    if not existing_lines:
        rendered.append("# HelloAGI local secrets")

    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={value}")

    p.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass
