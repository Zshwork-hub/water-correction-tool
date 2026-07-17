from __future__ import annotations


UI_COLORS = {
    "background": "#F3F4F6",
    "panel": "#FFFFFF",
    "primary": "#2563EB",
    "primary_active": "#1D4ED8",
    "success": "#15803D",
    "warning": "#B45309",
    "error": "#B91C1C",
    "text": "#111827",
    "muted": "#6B7280",
    "border": "#D1D5DB",
}

UI_SPACING = {
    "shell": 8,
    "section": 8,
    "control": 6,
    "control_height": 30,
}


def apply_ui_theme(style) -> None:
    style.configure("App.TFrame", background=UI_COLORS["background"])
    style.configure("Panel.TFrame", background=UI_COLORS["panel"])
    style.configure(
        "Nav.TButton",
        background=UI_COLORS["panel"],
        foreground=UI_COLORS["text"],
        padding=(12, 8),
        anchor="w",
    )
    style.configure(
        "NavSelected.TButton",
        background=UI_COLORS["primary"],
        foreground=UI_COLORS["panel"],
        padding=(12, 8),
        anchor="w",
    )
    style.map(
        "NavSelected.TButton",
        background=[("active", UI_COLORS["primary_active"])],
        foreground=[("disabled", UI_COLORS["border"]), ("!disabled", UI_COLORS["panel"])],
    )
    style.configure(
        "Primary.TButton",
        background=UI_COLORS["primary"],
        foreground=UI_COLORS["panel"],
        padding=(12, 6),
    )
    style.map(
        "Primary.TButton",
        background=[("active", UI_COLORS["primary_active"])],
        foreground=[("disabled", UI_COLORS["border"]), ("!disabled", UI_COLORS["panel"])],
    )
    style.configure(
        "Status.TLabel",
        background=UI_COLORS["background"],
        foreground=UI_COLORS["text"],
        padding=(8, 4),
    )
    style.configure(
        "Muted.TLabel",
        background=UI_COLORS["panel"],
        foreground=UI_COLORS["muted"],
    )