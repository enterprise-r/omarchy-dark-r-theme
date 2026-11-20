#!/usr/bin/env python3
"""Keep Dark-R window geometry in looknfeel.lua while Dark-R is the theme.

omarchy theme set drops every .lua file from a cloned theme, so Dark-R's gaps,
border width, rounding and shadow cannot ship as hyprland.lua. This hook
writes a managed block into ~/.config/hypr/looknfeel.lua when Dark-R is the
active theme, and takes it out when another theme is applied, so that theme
gets Omarchy's own geometry. The rest of the file is left alone. Hyprland
reloads the file on save.

The hook also says when the installed Dark-R hooks and bar widgets are older
than the theme checkout, which happens after omarchy theme update, once per
checkout state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dark_r_common import (  # noqa: E402  (installed beside this hook)
    THEME_NAME,
    active_theme_name,
    insert_geometry_block,
    looknfeel_path,
    remove_geometry_block,
    source_digest,
)


def write_geometry(home: Path, enable: bool) -> bool:
    """Insert or remove the block. Returns True when the file changed."""
    try:
        path = looknfeel_path(home)
    except RuntimeError:
        return False
    exists = path.is_file()
    if not exists and not enable:
        return False
    original = path.read_text() if exists else ""
    text = insert_geometry_block(original) if enable else remove_geometry_block(original)
    if text == original:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".dark-r-tmp")
    tmp.write_text(text)
    tmp.replace(path)
    return True


def state_dir(home: Path) -> Path:
    return home / ".local/state/omarchy-dark-r"


def stale_install(home: Path) -> str | None:
    """The checkout digest when it differs from the installed copies and was not yet reported."""
    try:
        record = json.loads((state_dir(home) / "install.json").read_text())
    except (OSError, ValueError):
        return None
    installed = record.get("source_digest") if isinstance(record, dict) else None
    checkout = home / ".config/omarchy/themes" / THEME_NAME
    if not installed or not (checkout / "plugins").is_dir():
        return None
    try:
        current = source_digest(checkout)
    except OSError:
        return None
    if current == installed:
        return None
    try:
        seen = json.loads((state_dir(home) / "notice.json").read_text()).get("digest")
    except (OSError, ValueError, AttributeError):
        seen = None
    return None if seen == current else current


def notify_stale(home: Path, digest: str) -> None:
    subprocess.run(
        [
            # The glyph of Omarchy's own update indicator.
            "omarchy-notification-send", "-g", "",
            "Dark-R was updated",
            "Run ./install.sh --reinstall in ~/.config/omarchy/themes/dark-r to update the bar and hooks.",
        ],
        check=False,
        capture_output=True,
    )
    notice = state_dir(home) / "notice.json"
    notice.parent.mkdir(parents=True, exist_ok=True)
    notice.write_text(json.dumps({"digest": digest}) + "\n")


def apply(home: Path, clear: bool = False, notify: bool = True) -> int:
    enable = not clear and active_theme_name(home) == THEME_NAME
    write_geometry(home, enable)
    if notify and not clear:
        digest = stale_install(home)
        if digest:
            notify_stale(home, digest)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove the Dark-R geometry block")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--no-notify", action="store_true", help="do not report an outdated install")
    args = parser.parse_args()
    return apply(args.home, clear=args.clear, notify=not args.no_notify)


if __name__ == "__main__":
    raise SystemExit(main())
