#!/usr/bin/env python3
"""Build the theme files that derive from colors.toml.

colors.toml is the one source of the palette. This writes:

  shell.toml          from templates/shell.toml.tpl
  vscode-theme.json   Omarchy's own VS Code template, rendered by Omarchy,
                      with the Dark-R workbench colors from vscode_surfaces.py
  chromium.theme      the color Chromium-family browsers build their frame,
                      toolbar, and new tab page from (see chromium_seed)

Omarchy uses a file a theme ships in place of the one it would generate, so
all three reach a theme installed with omarchy theme install, with no hook.

--check compares instead of writing, and exits 1 when a file is out of date.
vscode-theme.json needs Omarchy's renderer; without Omarchy it is skipped.

--assets also draws the boot screen images, which need Pillow and Omarchy:

  unlock.png          Omarchy's wordmark, each letter a palette color, as in
                      backgrounds/omarchy.webp. The boot and disk-unlock
                      screen shows it.
  preview-unlock.png  that screen, laid out as Omarchy's Plymouth theme does

--compress-preview shrinks preview.png after a new screenshot: 256 colors,
as the stock previews are, when that keeps every theme color exact and every
pixel close, and otherwise a lossless recompress.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dark_r_common import load_colors, roles  # noqa: E402
from vscode_surfaces import patch_theme  # noqa: E402

TOKEN = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
RENDERER = "omarchy-theme-set-templates"


def palette(colors_path: Path) -> dict[str, str]:
    data = tomllib.loads(colors_path.read_text())
    return {key: value for key, value in data.items() if isinstance(value, str)}


def render(template: str, values: dict[str, str]) -> str:
    def value(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise ValueError(f"templates refer to {key!r}, which colors.toml does not define")
        return values[key]
    return TOKEN.sub(value, template)


def build_shell(root: Path) -> str:
    return render((root / "templates/shell.toml.tpl").read_text(), palette(root / "colors.toml"))


def omarchy_vscode_theme(colors_path: Path) -> dict | None:
    """Omarchy's VS Code theme for this palette, rendered by Omarchy itself.

    The renderer writes into ~/.local/state/omarchy/current/next-theme, so it
    runs with HOME set to a scratch directory and touches nothing real.
    """
    if shutil.which(RENDERER) is None:
        return None
    with tempfile.TemporaryDirectory(prefix="dark-r-build-") as scratch:
        theme = Path(scratch) / ".local/state/omarchy/current/next-theme"
        theme.mkdir(parents=True)
        shutil.copy2(colors_path, theme / "colors.toml")
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        env["HOME"] = scratch
        subprocess.run([RENDERER], check=True, env=env, capture_output=True)
        return json.loads((theme / "vscode-theme.json").read_text())


def build_vscode(root: Path) -> str | None:
    generated = omarchy_vscode_theme(root / "colors.toml")
    if generated is None:
        return None
    patched = patch_theme(generated, load_colors(root / "colors.toml"))
    return json.dumps(patched, indent=4) + "\n"


# The seven letters of Omarchy's 800x188 wordmark take seven palette colors.
LETTER_COLORS = ("accent", "red", "orange", "yellow", "green", "cyan", "magenta")
# Column where each letter starts. C and H touch: H's crossbar begins at 584.
LETTER_STARTS = (0, 108, 266, 375, 493, 584, 711)


def omarchy_path() -> Path:
    return Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))


def wordmark_mask():
    """The alpha of Omarchy's wordmark, which every stock theme ships."""
    from PIL import Image
    for path in sorted((omarchy_path() / "themes").glob("*/unlock.png")):
        image = Image.open(path).convert("RGBA")
        if image.size == (800, 188):
            return image.getchannel("A")
    raise FileNotFoundError("no stock unlock.png in " + str(omarchy_path() / "themes"))


def build_unlock(root: Path):
    from PIL import Image
    colors = palette(root / "colors.toml")
    alpha = wordmark_mask()
    image = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    bounds = list(LETTER_STARTS) + [alpha.size[0]]
    for index, key in enumerate(LETTER_COLORS):
        color = Image.new("RGBA", (bounds[index + 1] - bounds[index], alpha.size[1]), colors[key])
        image.paste(color, (bounds[index], 0), alpha.crop((bounds[index], 0, bounds[index + 1], alpha.size[1])))
    return image


def tinted(path: Path, color: str, size: tuple[int, int] | None = None):
    """A Plymouth asset recolored as omarchy-plymouth-set does: RGB to the text color, alpha kept."""
    from PIL import Image
    image = Image.open(path).convert("RGBA")
    if size:
        image = image.resize(size, Image.LANCZOS)
    solid = Image.new("RGBA", image.size, color)
    solid.putalpha(image.getchannel("A"))
    return solid


def build_unlock_preview(root: Path, unlock):
    """The boot unlock screen at 1920x1080, placed as Omarchy's plymouth script does."""
    from PIL import Image
    colors = palette(root / "colors.toml")
    assets = omarchy_path() / "default/plymouth"
    width, height = 1920, 1080
    screen = Image.new("RGBA", (width, height), colors["background"])
    logo_x = width // 2 - unlock.width // 2
    logo_y = height // 2 - unlock.height // 2
    screen.alpha_composite(unlock, (logo_x, logo_y))
    entry = tinted(assets / "entry.png", colors["foreground"])
    entry_x = width // 2 - entry.width // 2
    entry_y = logo_y + unlock.height + 40
    screen.alpha_composite(entry, (entry_x, entry_y))
    lock_h = round(entry.height * 0.8)
    lock_w = round(84 * lock_h / 96)
    lock = tinted(assets / "lock.png", colors["foreground"], (lock_w, lock_h))
    screen.alpha_composite(lock, (entry_x - lock_w - 15, entry_y + entry.height // 2 - lock_h // 2))
    bullet = tinted(assets / "bullet.png", colors["foreground"], (7, 7))
    for index in range(4):
        screen.alpha_composite(bullet, (entry_x + 20 + index * 12, round(entry_y + entry.height / 2 - 3.5)))
    return screen.convert("RGB")


def build_assets(root: Path) -> None:
    unlock = build_unlock(root)
    unlock.save(root / "unlock.png", optimize=True)
    print("wrote unlock.png")
    preview = build_unlock_preview(root, unlock)
    preview.quantize(colors=256).save(root / "preview-unlock.png", optimize=True)
    print("wrote preview-unlock.png")


MAX_PREVIEW_ERROR = 24


def quantize_keeping_palette(image, theme_colors: list[str]):
    """256 colors, with every theme color among them, so a swatch keeps its exact hex.

    The other entries adapt to the rest of the screenshot. Pillow maps to a
    fixed palette through an approximate cache, so each distinct color is
    matched to its nearest entry here instead. Returns None when a
    theme-colored pixel would change, or any pixel would move by more than
    MAX_PREVIEW_ERROR in a channel: a colorful wallpaper behind glassy windows
    does not fit in 256 colors. Needs numpy.
    """
    import numpy as np
    from PIL import Image
    fixed = list(dict.fromkeys(c.lower() for c in theme_colors))[:128]
    adaptive = image.quantize(colors=256 - len(fixed), method=Image.Quantize.MEDIANCUT)
    entries = []
    for color in fixed:
        entries += [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    entries += adaptive.getpalette()[:3 * (256 - len(fixed))]
    entries += [0] * (768 - len(entries))
    table = np.array(entries, dtype=np.int32).reshape(256, 3)

    pixels = np.asarray(image, dtype=np.uint8).reshape(-1, 3)
    keys = (pixels[:, 0].astype(np.uint32) << 16) | (pixels[:, 1].astype(np.uint32) << 8) | pixels[:, 2]
    distinct, inverse = np.unique(keys, return_inverse=True)
    colors = np.stack([(distinct >> 16) & 255, (distinct >> 8) & 255, distinct & 255], axis=1).astype(np.int32)
    nearest = np.empty(len(colors), dtype=np.uint8)
    for begin in range(0, len(colors), 8192):
        chunk = colors[begin:begin + 8192]
        # The fixed theme entries come first, so an exact theme color wins a tie.
        nearest[begin:begin + 8192] = ((chunk[:, None, :] - table[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    indices = nearest[inverse.reshape(-1)]

    mapped = table[indices]
    themed = np.isin(keys, [int(c[1:], 16) for c in fixed])
    if not np.array_equal(mapped[themed], pixels[themed].astype(np.int32)):
        return None
    if int(np.abs(mapped - pixels.astype(np.int32)).max()) > MAX_PREVIEW_ERROR:
        return None
    result = Image.frombytes("P", image.size, indices.astype(np.uint8).tobytes())
    result.putpalette(entries)
    return result


def compress_preview(root: Path) -> None:
    from PIL import Image
    path = root / "preview.png"
    image = Image.open(path)
    if image.mode == "P":
        print("preview.png is already quantized")
        return
    image = image.convert("RGB")
    before = path.stat().st_size
    theme_colors = [v for v in palette(root / "colors.toml").values() if v.startswith("#") and len(v) == 7]
    result = quantize_keeping_palette(image, theme_colors)
    if result is None:
        image.save(path, optimize=True)
        print("preview.png: 256 colors would visibly change it; recompressed without loss")
    else:
        result.save(path, optimize=True)
    print(f"preview.png: {before // 1024} KB -> {path.stat().st_size // 1024} KB")


def chromium_seed(colors: dict[str, str]) -> str:
    """The BrowserThemeColor Omarchy hands Chromium, Chrome, Edge, and Brave.

    Chromium paints the tab strip in the seed itself and lightens it to about
    27% for the toolbar, the selected tab, and the new tab page, keeping its
    hue and saturation. A near-black seed with the saturation of background
    turns those bright purple. This seed carries the hue and saturation of the
    Firefox toolbar (the bar role) at the lightness of background, so the
    toolbar lands on the bar color and the strip stays dark, as in Firefox.
    """
    def hls(color: str) -> tuple[float, float, float]:
        return colorsys.rgb_to_hls(*(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    hue, _, saturation = hls(roles(colors)["bar"])
    _, lightness, _ = hls(colors["background"])
    return "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hls_to_rgb(hue, lightness, saturation))


def build_chromium(root: Path) -> str:
    seed = chromium_seed(load_colors(root / "colors.toml"))
    return ",".join(str(int(seed[i:i + 2], 16)) for i in (1, 3, 5)) + "\n"


def outputs(root: Path) -> dict[str, str | None]:
    return {
        "shell.toml": build_shell(root),
        "vscode-theme.json": build_vscode(root),
        "chromium.theme": build_chromium(root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report files that are out of date and change nothing")
    parser.add_argument("--assets", action="store_true", help="also draw unlock.png and preview-unlock.png")
    parser.add_argument("--compress-preview", action="store_true", help="shrink preview.png, without visible change")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.compress_preview:
        compress_preview(args.root)
        return 0
    stale = []
    for name, text in outputs(args.root).items():
        path = args.root / name
        if text is None:
            print(f"skipped {name}: {RENDERER} is not installed", file=sys.stderr)
            continue
        current = path.read_text() if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(name)
        else:
            path.write_text(text)
            print(f"wrote {name}")
    if stale:
        print("Out of date: " + ", ".join(stale) + ". Run python3 scripts/build.py.", file=sys.stderr)
        return 1
    if args.assets and not args.check:
        build_assets(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
