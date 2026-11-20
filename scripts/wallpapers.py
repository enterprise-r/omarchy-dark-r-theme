#!/usr/bin/env python3
"""Use pictures from ~/Pictures/Wallpapers as Dark-R backgrounds.

Omarchy cycles files placed directly in ~/.config/omarchy/backgrounds/dark-r/
and in the theme's backgrounds folder. This links each image and video placed
directly in ~/Pictures/Wallpapers into that user folder. Files in subfolders
are left out. The bundled theme wallpaper remains, and it is what shows when
the pictures folder is missing or empty.

The links are hard links when the picture is on the same filesystem, so the
path Omarchy records is the path it later cycles through. A copy is used
when a hard link is not possible. Names this hook created are listed in the
Dark-R state directory. Other files in the user background folder are left
alone.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dark_r_common import active_theme_name  # noqa: E402  (installed beside this hook)

THEME = "dark-r"
EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "mp4", "m4v", "mov", "webm", "mkv", "avi",
}


def pictures_dir(home: Path) -> Path:
    return home / "Pictures" / "Wallpapers"


def background_dir(home: Path) -> Path:
    return home / ".config" / "omarchy" / "backgrounds" / THEME


def manifest_path(home: Path) -> Path:
    return home / ".local" / "state" / "omarchy-dark-r" / "wallpapers.json"


def current_background(home: Path) -> Path | None:
    link = home / ".local/state/omarchy/current/background"
    try:
        if link.is_symlink():
            return Path(os.path.realpath(link))
        if link.is_file():
            return link.resolve()
    except OSError:
        return None
    return None


def same_file(left: Path, right: Path) -> bool:
    try:
        a = left.stat()
        b = right.stat()
    except OSError:
        return False
    return a.st_dev == b.st_dev and a.st_ino == b.st_ino


def load_manifest(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return {}
    return {str(name): str(source) for name, source in files.items()}


def save_manifest(path: Path, files: dict[str, str]) -> None:
    if not files:
        if path.exists() or path.is_symlink():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".dark-r-tmp")
    temp.write_text(json.dumps({"files": files}, indent=2) + "\n")
    temp.replace(path)


def collect(root: Path) -> list[Path]:
    """Image and video files placed directly in root. Subfolders are excluded."""
    if not root.is_dir():
        return []
    start = root.resolve() if root.is_symlink() else root
    found = []
    for path in start.iterdir():
        if path.name.startswith(".") or path.is_dir():
            continue
        if path.suffix.lower().lstrip(".") not in EXTENSIONS:
            continue
        if not path.is_file():
            continue
        found.append(path)
    return sorted(found, key=lambda item: item.name)


def link_name(root: Path, path: Path) -> str:
    start = root.resolve() if root.is_symlink() else root
    return "__".join(path.relative_to(start).parts)


def allocate(directory: Path, name: str, owned: set[str], used: set[str]) -> str:
    """A free name. A name this hook already owns can be replaced."""
    suffix = Path(name).suffix
    stem = name[:-len(suffix)] if suffix else name
    number = 1
    while True:
        candidate = name if number == 1 else f"{stem}-{number}{suffix}"
        number += 1
        if candidate in used:
            continue
        dest = directory / candidate
        taken = dest.exists() or dest.is_symlink()
        if candidate in owned or not taken:
            used.add(candidate)
            return candidate


def place(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if not dest.is_symlink() and same_file(dest, src):
            return
        dest.unlink()
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def remove_owned(directory: Path, names) -> None:
    for name in names:
        path = directory / name
        if path.is_symlink() or path.is_file():
            path.unlink()
    if directory.is_dir() and not directory.is_symlink():
        try:
            directory.rmdir()
        except OSError:
            pass


def theme_wallpaper(home: Path) -> Path | None:
    """The bundled wallpaper, used when the user's folder has nothing to show.

    Several images can ship with the theme. warp-cruise.png stays the one
    this returns, so emptying ~/Pictures/Wallpapers comes back to it.
    """
    user = background_dir(home).resolve()
    directories = (
        home / ".config/omarchy/themes" / THEME / "backgrounds",
        home / ".local/state/omarchy/current/theme/backgrounds",
    )
    for directory in directories:
        if not directory.is_dir() or directory.is_symlink():
            continue
        if directory.resolve() == user:
            continue
        files = sorted(
            path for path in directory.iterdir()
            if path.is_file() and not path.is_symlink()
            and path.suffix.lower().lstrip(".") in EXTENSIONS
        )
        preferred = [path for path in files if path.name == "warp-cruise.png"]
        if preferred:
            return preferred[0]
        if files:
            return files[0]
    return None


def sync(home: Path) -> Path | None:
    """Refresh the linked wallpapers. Return a path to show, or None to keep the current one.

    The returned path is only for Dark-R. Other themes keep their own wallpaper.
    """
    root = pictures_dir(home)
    directory = background_dir(home)
    record = manifest_path(home)
    previous = load_manifest(record)
    owned = set(previous)
    sources = collect(root) if root.is_dir() else []

    planned = []
    used = set()
    for src in sources:
        planned.append((src, allocate(directory, link_name(root, src), owned, used)))

    remove_owned(directory, [name for name in previous if name not in used])
    placed = {}
    for src, name in planned:
        dest = directory / name
        try:
            place(src, dest)
        except OSError:
            continue
        placed[name] = str(src)
    save_manifest(record, placed)

    if active_theme_name(home) != THEME:
        return None

    current = current_background(home)
    entries = [(src, directory / name) for src, name in planned if (directory / name).exists()]
    if current is not None:
        for src, dest in entries:
            if same_file(current, src) or same_file(current, dest):
                if Path(os.path.realpath(current)) != Path(os.path.realpath(dest)):
                    return dest
                return None
    if not entries:
        if current is not None and not current.exists() and previous:
            return theme_wallpaper(home)
        return None
    newest = max(entries, key=lambda item: (item[0].stat().st_mtime_ns, str(item[0])))
    return newest[1]


def clear(home: Path) -> Path | None:
    """Remove wallpapers this hook added. Return the bundled wallpaper when that was showing."""
    directory = background_dir(home)
    record = manifest_path(home)
    previous = load_manifest(record)
    current = current_background(home)
    showing_ours = False
    if current is not None and active_theme_name(home) == THEME:
        for name in previous:
            path = directory / name
            if path.exists() and same_file(current, path):
                showing_ours = True
                break
        if previous and not current.exists():
            showing_ours = True
    remove_owned(directory, previous.keys())
    if record.exists() or record.is_symlink():
        record.unlink()
    if showing_ours:
        return theme_wallpaper(home)
    return None


def publish(path: Path) -> None:
    subprocess.run(["omarchy", "theme", "bg", "set", str(path)], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove wallpapers added from ~/Pictures/Wallpapers")
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    chosen = clear(args.home) if args.clear else sync(args.home)
    if chosen is not None and args.home.resolve() == Path.home().resolve():
        publish(chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
