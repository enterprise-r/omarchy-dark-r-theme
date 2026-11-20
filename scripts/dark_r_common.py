"""Code shared by the Dark-R installer and its theme-set hooks.

The installer copies this module next to the hooks in ~/.config/omarchy/hooks/.
Omarchy's hook runner only executes files in theme-set.d/, so it never runs
on its own. Each hook imports it from its own directory.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tomllib

THEME_NAME = "dark-r"


def hex_ok(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def luminance(color: str) -> float:
    """WCAG relative luminance."""
    def channel(i: int) -> float:
        c = int(color[i:i + 2], 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def blend(top: str, bottom: str, alpha: float) -> str:
    """top drawn at alpha over an opaque bottom."""
    out = "#"
    for i in (1, 3, 5):
        a = int(top[i:i + 2], 16)
        b = int(bottom[i:i + 2], 16)
        out += "%02x" % round(alpha * a + (1 - alpha) * b)
    return out


def on_color(surface: str, background: str, foreground: str) -> str:
    """Readable text on a filled surface, preferring the theme's own colors."""
    best = foreground
    best_ratio = 0.0
    for candidate in (background, foreground, "#ffffff", "#000000"):
        ratio = contrast(surface, candidate)
        if candidate in ("#ffffff", "#000000") and best_ratio >= 4.5:
            continue
        if ratio > best_ratio:
            best = candidate
            best_ratio = ratio
    return best


REQUIRED = ("background", "foreground", "accent", "red", "green")
OPTIONAL = (
    "lighter_background",
    "selection",
    "dark_foreground",
    "bright_foreground",
    "yellow",
    "orange",
    "cyan",
    "blue",
    "magenta",
    "brown",
    "bright_red",
    "bright_yellow",
    "bright_green",
    "bright_cyan",
    "bright_magenta",
    "hyprland_inactive_border",
    "hyprland_active_border",
)


def load_colors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    for key in REQUIRED:
        if not hex_ok(data.get(key)):
            raise ValueError(f"bad or missing color {key!r} in {path}")
    out = {key: data[key] for key in REQUIRED}
    for key in OPTIONAL:
        if hex_ok(data.get(key)):
            out[key] = data[key]
    return out


def roles(colors: dict[str, str]) -> dict[str, str]:
    """Dark-R roles from colors.toml.

    bar      hyprland_inactive_border: header bars and the browser toolbar
    line     hyprland_inactive_border: text selection, quiet separators
    edge     dark_foreground: card, panel and field borders
    hover    accent: pointer and keyboard cursor
    primary  green: current, chosen, checked, suggested, selected tab
    focus    bright_foreground: keyboard focus ring
    active   cyan: focused field and the active window
    link     bright_magenta, hover bright_yellow, visited yellow
    notices  info blue, ok green, warn accent, error red
    destructive buttons stay red; hover brightens them, as primary
    """
    bg = colors["background"]
    fg = colors["foreground"]
    accent = colors["accent"]
    green = colors["green"]
    card = colors.get("lighter_background", bg)
    line = colors.get("hyprland_inactive_border", colors.get("selection", card))
    magenta = colors.get("magenta", accent)
    return {
        "bg": bg,
        "fg": fg,
        "card": card,
        "bar": line,
        "line": line,
        "edge": colors.get("dark_foreground", fg),
        "dim": colors.get("dark_foreground", fg),
        "bright": colors.get("bright_foreground", fg),
        "hover": accent,
        "primary": green,
        "primary_hover": colors.get("bright_green", green),
        "focus": colors.get("bright_foreground", fg),
        "active": colors.get("hyprland_active_border", magenta),
        "link": colors.get("bright_magenta", magenta),
        "link_hover": colors.get("bright_yellow", accent),
        "link_visited": colors.get("yellow", magenta),
        "info": colors.get("blue", accent),
        "ok": green,
        "warn": accent,
        "error": colors["red"],
        "error_hover": colors.get("bright_red", colors["red"]),
    }


def active_theme_name(home: Path) -> str:
    path = home / ".local/state/omarchy/current/theme.name"
    try:
        return path.read_text().strip()
    except OSError:
        return ""


# Window geometry. omarchy theme set drops every .lua file from a cloned
# theme, so the installer keeps this block in ~/.config/hypr/looknfeel.lua.
# The geometry hook writes it while Dark-R is the active theme and takes it
# out for any other theme. The bar pills read the same rounding through
# Style.cornerRadius.
GEOMETRY = {
    "gaps_in": 4,
    "gaps_out": 8,
    "border_size": 1,
    "rounding": 10,
}
GEOMETRY_BEGIN = "-- BEGIN Dark-R geometry\n"
GEOMETRY_END = "-- END Dark-R geometry\n"
# Written by Dark-R before 2.0, which only set the rounding.
LEGACY_BEGIN = "-- BEGIN Dark-R corners\n"
LEGACY_END = "-- END Dark-R corners\n"
GEOMETRY_BLOCK = (
    GEOMETRY_BEGIN
    + "hl.config({\n"
    + "  general = {\n"
    + f"    gaps_in = {GEOMETRY['gaps_in']},\n"
    + f"    gaps_out = {GEOMETRY['gaps_out']},\n"
    + f"    border_size = {GEOMETRY['border_size']},\n"
    + "  },\n"
    + "  decoration = {\n"
    + f"    rounding = {GEOMETRY['rounding']},\n"
    + "    shadow = { enabled = false },\n"
    + "  },\n"
    + "})\n"
    + GEOMETRY_END
)


def looknfeel_path(home: Path) -> Path:
    """The file Hyprland reads, following a symlink that stays inside home."""
    path = home / ".config/hypr/looknfeel.lua"
    if path.is_symlink():
        target = path.resolve()
        if not target.is_relative_to(home) or not target.is_file():
            raise RuntimeError("Refusing to edit looknfeel.lua symlink: " + str(path))
        return target
    return path


def _strip(text: str, begin: str, end: str) -> str:
    start = text.find(begin)
    if start < 0:
        return text
    stop = text.find(end, start)
    if stop < 0:
        return text
    stop += len(end)
    if start >= 1 and text[start - 1] == "\n":
        start -= 1
    return text[:start] + text[stop:]


def remove_geometry_block(text: str) -> str:
    """Drop the Dark-R block, and the rounding-only block of older installs."""
    return _strip(_strip(text, GEOMETRY_BEGIN, GEOMETRY_END), LEGACY_BEGIN, LEGACY_END)


def insert_geometry_block(text: str) -> str:
    """Append the current block, replacing an older or stale one."""
    if GEOMETRY_BLOCK in text and LEGACY_BEGIN not in text:
        return text
    text = remove_geometry_block(text)
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    return text + GEOMETRY_BLOCK


# Files the installer copies out of this checkout. A change to any of them
# means the installed copies are older than the checkout.
INSTALLED_SOURCE_SKIP = {"manage.py", "build.py"}


def source_digest(root: Path) -> str:
    h = hashlib.sha256()
    files = [p for p in sorted((root / "plugins").rglob("*")) if p.is_file()]
    files += [
        p for p in sorted((root / "scripts").glob("*.py"))
        if p.is_file() and p.name not in INSTALLED_SOURCE_SKIP
    ]
    for path in files:
        h.update(str(path.relative_to(root)).encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()
