from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Mapping


DEFAULT_SHORTCUTS: Dict[str, str] = {"brush": "b", "eraser": "e"}
SHORTCUT_TOOLS = ("brush", "eraser")


def normalize_shortcut(value: str) -> str:
    key = value.strip().lower()
    if len(key) != 1 or key.isspace():
        return ""
    return key


def load_shortcuts(path: Path, defaults: Mapping[str, str] | None = None) -> Dict[str, str]:
    shortcuts = dict(defaults or DEFAULT_SHORTCUTS)
    if not path.exists():
        return shortcuts
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return shortcuts
    if not isinstance(payload, dict):
        return shortcuts

    loaded = dict(shortcuts)
    for tool in SHORTCUT_TOOLS:
        value = payload.get(tool)
        key = normalize_shortcut(value) if isinstance(value, str) else ""
        if key:
            loaded[tool] = key
    if loaded.get("brush") == loaded.get("eraser"):
        return shortcuts
    return loaded


def save_shortcuts(path: Path, shortcuts: Mapping[str, str]) -> None:
    payload = {tool: shortcuts.get(tool, DEFAULT_SHORTCUTS[tool]) for tool in SHORTCUT_TOOLS}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def shortcut_label(shortcuts: Mapping[str, str], tool: str) -> str:
    return shortcuts.get(tool, "").upper()
