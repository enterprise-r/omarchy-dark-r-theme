#!/usr/bin/env python3
"""Install, reinstall, or uninstall the optional Dark-R extensions.

The theme works without this. omarchy theme install gives the palette, shell
colors, VS Code colors and wallpapers. This adds what a theme cannot ship:
application colors for GTK and Firefox, the Dark-R bar, wallpapers from
~/Pictures/Wallpapers, and window geometry. It runs from the theme checkout
and never copies or replaces that directory. Update the theme with
omarchy theme update, then run ./install.sh --reinstall.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dark_r_common as common  # noqa: E402

THEME = common.THEME_NAME
# Formats an older install wrote into shell.json. The Dark-R clock no longer
# reads them; uninstall still puts the previous label back on omarchy.clock.
THEME_CLOCK_FORMAT = 'yyyyMM.dd ddd HH:mm'
THEME_CLOCK_FORMATS = {"'STARDATE' ddd HH:mm", THEME_CLOCK_FORMAT}
# Used when the label from before install was itself a theme label.
STOCK_CLOCK_FORMAT = 'dddd HH:mm'
# Stock widgets the bar component replaces with a Dark-R copy.
SOURCES = ['menu', 'clock', 'workspaces', 'indicators']
# Widgets Dark-R replaced before 2.0. Their copies changed nothing a theme
# needs, so the stock widget comes back. Reinstall and uninstall map them back.
RETIRED_SOURCES = ['weather', 'keyboard-layout', 'system-update']
RETIRED_PLUGINS = {'dark-r.' + name for name in RETIRED_SOURCES}
# Omarchy uses the vscode-theme.json this theme ships, so that hook is gone.
RETIRED_HOOKS = {'dark-r-vscode-surfaces.py', 'dark-r-vscode-surfaces.sh'}

# Parts of the installer. The theme itself needs none of them.
COMPONENTS = ('gtk', 'firefox', 'bar', 'wallpapers')
LIGHT_COMPONENTS = ('gtk', 'firefox', 'wallpapers')
# Shared code the hooks import. It sits beside them and is never run itself.
SUPPORT_MODULE = ('dark_r_common.py', 'scripts/dark_r_common.py')
# (installed helper, theme-set wrapper, path inside this repo, component).
# A hook with no component comes with every install.
HOOKS = (
    # GTK3 themes (Adwaita-dark, Omagtk) compile their colors in, and GTK4 and
    # libadwaita ignore the GTK theme name. GIMP 3 is covered by the GTK3 hook.
    ('dark-r-gtk3.py', 'dark-r-gtk3.sh', 'scripts/gtk3.py', 'gtk'),
    ('dark-r-gtk4-libadwaita.py', 'dark-r-gtk4.sh', 'scripts/gtk4-libadwaita.py', 'gtk'),
    # Firefox chrome follows GTK system colors, not the libadwaita palette.
    ('dark-r-firefox-chrome.py', 'dark-r-firefox.sh', 'scripts/firefox-chrome.py', 'firefox'),
    # ~/Pictures/Wallpapers, when it has images, supplies this theme's wallpapers.
    ('dark-r-wallpapers.py', 'dark-r-wallpapers.sh', 'scripts/wallpapers.py', 'wallpapers'),
    # Gaps, border, rounding and shadow while Dark-R is the active theme.
    ('dark-r-geometry.py', 'dark-r-geometry.sh', 'scripts/geometry.py', None),
)
MANAGED_HOOK_NAMES = {SUPPORT_MODULE[0]} | {name for hook in HOOKS for name in hook[:2]}

def hooks_for(components):
    return [hook for hook in HOOKS if hook[3] is None or hook[3] in components]

def parse_components(names):
    unknown = [name for name in names if name not in COMPONENTS]
    if unknown:
        raise ValueError('Unknown component: ' + ', '.join(unknown) + '. Choose from: ' + ', '.join(COMPONENTS) + '.')
    return [name for name in COMPONENTS if name in names]

def load_record(record_file):
    """Read the install record, upgrading one written before components existed."""
    record = json.loads(record_file.read_text())
    if not isinstance(record, dict) or not isinstance(record.get('targets'), list):
        raise RuntimeError('Unsupported Dark-R install record.')
    if record.get('version') == 1:
        record['components'] = list(LIGHT_COMPONENTS if record.get('theme_only') else COMPONENTS)
        record.pop('theme_only', None)
        if 'corners_created_looknfeel' in record:
            record['geometry_created_looknfeel'] = record.pop('corners_created_looknfeel')
        record['version'] = 2
    if record.get('version') != 2 or not isinstance(record.get('components'), list):
        raise RuntimeError('Unsupported Dark-R install record.')
    return record

def write_json(path, data):
    # A symlink to a regular file is a versioned dotfile. Replace that file so
    # the link stays. os.replace on the link itself would remove the link.
    dest = path
    if path.is_symlink():
        dest = Path(os.path.realpath(path))
        if not dest.is_file():
            raise RuntimeError('Refusing to write through symlink: ' + str(path))
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + '.dark-r-tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(dest)

def digest(path):
    # Hash a symlink as a link. Never follow it: a wallpaper folder is often
    # linked from the theme, and reading through it would hash the user's pictures.
    if path.is_symlink():
        h = hashlib.sha256()
        h.update(b'link:')
        h.update(os.readlink(path).encode())
        return h.hexdigest()
    if not path.exists():
        return None
    h = hashlib.sha256()
    files = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_symlink() or p.is_file())
    for file in files:
        rel = file.name if path.is_file() else str(file.relative_to(path))
        h.update(rel.encode())
        if file.is_symlink():
            h.update(b'link:')
            h.update(os.readlink(file).encode())
        else:
            h.update(file.read_bytes())
    return h.hexdigest()

def regular_files_equal(installed, incoming):
    """True when every regular file in installed has the same bytes in incoming.

    Symlinks are ignored and not followed. A file that exists only in installed
    is a local addition. Files that exist only in incoming are updates.
    """
    def files(root):
        if root.is_symlink() or not root.exists():
            return {}
        found = {}
        paths = [root] if root.is_file() else [p for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
        for file in paths:
            rel = '.' if root.is_file() else str(file.relative_to(root))
            found[rel] = file.read_bytes()
        return found
    inst = files(installed)
    inc = files(incoming)
    if set(inst) - set(inc):
        return False
    return all(inc[rel] == data for rel, data in inst.items())

def copy_path(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        dest.symlink_to(os.readlink(src))
    elif src.is_dir():
        shutil.copytree(src, dest, symlinks=True)
    else:
        shutil.copy2(src, dest)

def remove(path):
    # is_dir() follows links. Unlink a symlink itself and leave its target.
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

def restore_symlinks(snapshot, dest):
    if snapshot.is_symlink() or not snapshot.is_dir():
        return
    for link in sorted(p for p in snapshot.rglob('*') if p.is_symlink()):
        target = dest / link.relative_to(snapshot)
        if target.exists() or target.is_symlink():
            remove(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(os.readlink(link))

def locally_edited(target, recorded, incoming=None):
    """A hand edit blocks reinstall and uninstall. A nested symlink does not.

    Reinstall may still refresh regular files that match the incoming tree.
    The link itself is preserved and is never followed.
    """
    if target.is_symlink() or not target.exists():
        return False
    if digest(target) == recorded:
        return False
    if incoming is not None and regular_files_equal(target, incoming):
        return False
    if incoming is None and target.is_dir() and any(p.is_symlink() for p in target.rglob('*')):
        return False
    return True

CLUSTER = ('centerBegin', 'center', 'centerEnd')

def find_entry(layout, widget_id):
    for section, entries in layout.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get('id') == widget_id:
                return section, index
    return None, None

def exchange(layout, left_id, right_id):
    left = find_entry(layout, left_id)
    right = find_entry(layout, right_id)
    if left[0] is None or right[0] is None or left == right:
        return False
    # The right-hand side is evaluated first, so this is safe in one section.
    layout[left[0]][left[1]], layout[right[0]][right[1]] = layout[right[0]][right[1]], layout[left[0]][left[1]]
    return True

def cluster_ids(layout):
    found = {}
    for name in CLUSTER:
        entries = layout.get(name)
        if not isinstance(entries, list):
            found[name] = []
            continue
        found[name] = [entry.get('id') for entry in entries if isinstance(entry, dict)]
    return found

def pin_workspaces(layout):
    """Keep the workspace indicator as the only widget in the center box.

    Buttons that share that box slide it when they grow. Neighbors hang off
    the side they were already on, which is where the bar lets them grow.
    """
    section, index = find_entry(layout, 'dark-r.workspaces')
    if section not in CLUSTER:
        return False
    entries = list(layout.get(section) or [])
    if section == 'center' and len(entries) == 1:
        return False
    before = entries[:index]
    widget = entries[index]
    after = entries[index + 1:]
    begin = list(layout.get('centerBegin') or [])
    center = list(layout.get('center') or [])
    end = list(layout.get('centerEnd') or [])
    if section == 'center':
        begin = begin + before
        center = [widget]
        end = after + end
    elif section == 'centerBegin':
        begin = before
        end = after + center + end
        center = [widget]
    else:
        begin = begin + center + before
        center = [widget]
        end = after
    layout['centerBegin'] = begin
    layout['center'] = center
    layout['centerEnd'] = end
    return True

def restore_cluster(layout, before_ids):
    wanted = []
    for name in CLUSTER:
        for widget_id in before_ids.get(name, []):
            wanted.append((name, widget_id))
    wanted_ids = {widget_id for _, widget_id in wanted}
    found = {}
    leftover = {name: [] for name in CLUSTER}
    for name in CLUSTER:
        for entry in list(layout.get(name) or []):
            widget_id = entry.get('id') if isinstance(entry, dict) else None
            if widget_id in wanted_ids and widget_id not in found:
                found[widget_id] = entry
            else:
                leftover[name].append(entry)
    for name in CLUSTER:
        layout[name] = [found[widget_id] for widget_id in before_ids.get(name, []) if widget_id in found]
        layout[name].extend(leftover[name])

def place_calendar_and_workspaces(bar):
    """Trade the calendar with the workspace indicator, then center the workspaces.

    A custom replacement of either widget is left where it is. The returned
    record is what uninstall reverses.
    """
    placement = {'swapped': False, 'pinned': False, 'cluster': None, 'cleared_center_anchor': False}
    layout = bar['layout']
    if find_entry(layout, 'dark-r.clock')[0] is None or find_entry(layout, 'dark-r.workspaces')[0] is None:
        return placement
    if not exchange(layout, 'dark-r.clock', 'dark-r.workspaces'):
        return placement
    placement['swapped'] = True
    placement['cluster'] = cluster_ids(layout)
    placement['pinned'] = pin_workspaces(layout)
    if bar.get('centerAnchor') in ('dark-r.clock', 'omarchy.clock'):
        # The center section is the pin. A leftover clock anchor would follow
        # the calendar after it leaves the middle.
        bar.pop('centerAnchor', None)
        placement['cleared_center_anchor'] = True
    return placement

def patch_shell(original):
    d = copy.deepcopy(original)
    if d.get('version') != 1 or not isinstance(d.get('bar', {}).get('layout'), dict):
        raise RuntimeError('Unsupported shell.json format; no configuration was changed.')
    # This edition is designed for horizontal bars; do not silently move a user's bar.
    if d['bar'].get('position', 'top') not in ['top', 'bottom']:
        raise RuntimeError('Dark-R requires a top or bottom bar. Move your bar first, or use --light to keep the standard bar.')
    changed = {}
    for entries in d['bar']['layout'].values():
        for entry in entries:
            source = entry.get('id', '')
            if source in ['omarchy.' + name for name in SOURCES]:
                target = source.replace('omarchy.', 'dark-r.', 1)
                changed[target] = copy.deepcopy(entry)
                entry['id'] = target
    anchor = d['bar'].get('centerAnchor')
    if anchor == 'omarchy.clock' and 'dark-r.clock' in changed:
        d['bar']['centerAnchor'] = 'dark-r.clock'
    placement = place_calendar_and_workspaces(d['bar'])
    # Stars stay in the layout and start hidden. A right-click on the bar shows them.
    left = d['bar']['layout'].setdefault('left', [])
    if not any(entry.get('id') == 'dark-r.stars' for entry in left):
        left.append({'id': 'dark-r.stars', 'shown': False})
    right = d['bar']['layout'].setdefault('right', [])
    right.append({'id': 'dark-r.plate'})
    # Menu actions still route to the native menu; the clone only styles its bar entry.
    return d, changed, placement

def replaced_entry(target, record):
    """The entry a dark-r widget replaced, also for widgets added after install."""
    if target in record['replaced']:
        return record['replaced'][target]
    name = target.split('.', 1)[1] if target.startswith('dark-r.') else None
    if name not in SOURCES and name not in RETIRED_SOURCES:
        return None
    source = 'omarchy.' + name
    layout = (record.get('before_shell') or {}).get('bar', {}).get('layout', {})
    section, index = find_entry(layout, source) if isinstance(layout, dict) else (None, None)
    return copy.deepcopy(layout[section][index]) if section is not None else {'id': source}

def stock_clock_format(omarchy_path=None):
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    try:
        stock = json.loads((omarchy_path / 'config/omarchy/shell.json').read_text())
        section, index = find_entry(stock['bar']['layout'], 'omarchy.clock')
        return stock['bar']['layout'][section][index]['format']
    except (OSError, ValueError, KeyError, TypeError):
        return STOCK_CLOCK_FORMAT

def unpatch_shell(current, record, clock_format=STOCK_CLOCK_FORMAT):
    d = copy.deepcopy(current)
    layout = d.get('bar', {}).get('layout', {})
    placement = record.get('bar_place') or {}
    # Reverse the pin before the swap, so each entry keeps edits made after install.
    # A bar already restored has no dark-r.workspaces; leave its order alone.
    if find_entry(layout, 'dark-r.workspaces')[0] is not None:
        if placement.get('pinned') and placement.get('cluster'):
            restore_cluster(layout, placement['cluster'])
        if placement.get('swapped'):
            exchange(layout, 'dark-r.clock', 'dark-r.workspaces')
    for section, entries in layout.items():
        result = []
        for entry in entries:
            target = entry.get('id')
            if target in ['dark-r.stars', 'dark-r.band', 'dark-r.plate']:
                continue
            before = replaced_entry(target, record)
            if before is not None:
                entry = copy.deepcopy(entry)
                entry['id'] = before['id']
                if entry['id'] == 'omarchy.clock' and entry.get('format') in THEME_CLOCK_FORMATS:
                    previous = before.get('format')
                    entry['format'] = previous if previous and previous not in THEME_CLOCK_FORMATS else clock_format
            result.append(entry)
        layout[section] = result
    before_bar = record.get('before_shell', {}).get('bar', {})
    if placement.get('cleared_center_anchor'):
        previous = before_bar.get('centerAnchor')
        if previous:
            d['bar']['centerAnchor'] = previous
        else:
            d['bar'].pop('centerAnchor', None)
    elif d.get('bar', {}).get('centerAnchor') == 'dark-r.clock':
        d['bar']['centerAnchor'] = before_bar.get('centerAnchor', '')
    before_layout = before_bar.get('layout', {})
    for name in CLUSTER:
        if name not in before_layout and not layout.get(name):
            layout.pop(name, None)
    return d

def apply_geometry(home):
    """Add the Dark-R geometry block to looknfeel.lua.

    Returns the previous text, or None when this call created the file, and
    whether this call created it.
    """
    path = common.looknfeel_path(home)
    created = not path.exists()
    original = None if created else path.read_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(common.insert_geometry_block('' if original is None else original))
    return original, created

def restore_geometry(home, geometry):
    """Undo apply_geometry using the tuple it returned."""
    original, created = geometry
    path = common.looknfeel_path(home)
    if created:
        if path.exists() and not path.is_symlink():
            path.unlink()
        return
    if original is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(original)

def remove_geometry(home, created=False):
    """Drop the Dark-R block, old or new, and keep the rest of looknfeel.lua."""
    link = home / '.config/hypr/looknfeel.lua'
    if not link.exists() and not link.is_symlink():
        return
    path = common.looknfeel_path(home)
    if not path.exists() or path.is_symlink():
        return
    text = common.remove_geometry_block(path.read_text())
    if created and text.strip() == '':
        path.unlink()
    else:
        path.write_text(text)

def check_hyprland():
    result = subprocess.run(['hyprctl', 'configerrors'], check=True, capture_output=True, text=True)
    if result.stdout.strip() not in ['', 'ok']:
        raise RuntimeError('Hyprland rejected the configuration: ' + result.stdout.strip())

def paths(home):
    return home / '.config/omarchy', home / '.local/state/omarchy-dark-r'

def theme_directory(config):
    return config / 'themes' / THEME

def is_theme_checkout(path):
    """True when Omarchy cloned the theme here. Do not delete or replace it.

    A worktree stores a gitdir file at .git rather than a directory.
    A symlink is the user's own theme and is left to the existing refusal.
    """
    return path.is_dir() and not path.is_symlink() and (path / '.git').exists()

def same_path(left, right):
    return left.resolve() == right.resolve()

def require_checkout_source(source, installed):
    if same_path(source, installed):
        return
    raise RuntimeError(
        'The Dark-R theme at ' + str(installed) + ' is a git checkout. '
        'Run ./install.sh from that directory. The installer does not replace it. '
        'Update the theme with git pull. A second omarchy theme install deletes the checkout.'
    )

def require_theme_checkout(home, source):
    """This repository is the theme. Refuse to copy one into place."""
    installed = theme_directory(paths(home)[0])
    if not is_theme_checkout(installed):
        raise RuntimeError(
            'Dark-R installs from the git checkout at ' + str(installed) + '. '
            'Clone the theme there and run ./install.sh from that directory.'
        )
    require_checkout_source(source, installed)
    return installed

def without_theme_target(targets, config):
    """Drop a theme-directory entry left by an older installer. Never delete the checkout."""
    installed = theme_directory(config)
    return [entry for entry in targets if not same_path(Path(entry['path']), installed)]

def stage_hooks(stage, source, components):
    """Stage the hooks for these components, and the module they share."""
    module, relative = SUPPORT_MODULE
    shutil.copy2(source / relative, stage / module)
    for helper_name, wrapper_name, relative, _component in hooks_for(components):
        helper = stage / helper_name
        shutil.copy2(source / relative, helper)
        helper.chmod(0o755)
        # Theme hooks are executed with bash, which does not honor a Python shebang.
        wrapper = stage / wrapper_name
        wrapper.write_text(
            '#!/bin/bash\n'
            f'exec python3 "$HOME/.config/omarchy/hooks/{helper_name}"\n'
        )
        wrapper.chmod(0o755)

def hook_targets(config, stage, components):
    targets = [(stage / SUPPORT_MODULE[0], config / 'hooks' / SUPPORT_MODULE[0])]
    for helper_name, wrapper_name, _relative, _component in hooks_for(components):
        targets.append((stage / helper_name, config / 'hooks' / helper_name))
        targets.append((stage / wrapper_name, config / 'hooks/theme-set.d' / wrapper_name))
    return targets

def plugin_targets(config, source):
    return [(plugin, config / 'plugins' / plugin.name) for plugin in sorted((source / 'plugins').iterdir()) if plugin.is_dir()]

def is_retired(target):
    return target.name in RETIRED_HOOKS or ('/plugins/' in str(target) and target.name in RETIRED_PLUGINS)

def run_hook(home, installed_name, repo_name, extra_args=()):
    script = (home or Path.home()) / '.config/omarchy/hooks' / installed_name
    if not script.is_file():
        script = ROOT / 'scripts' / repo_name
    if not script.is_file():
        return
    cmd = [sys.executable, str(script), *extra_args]
    if home is not None:
        cmd.extend(['--home', str(home)])
    subprocess.run(cmd, check=False)

def apply_hooks(components, home=None):
    for helper_name, _wrapper, relative, _component in hooks_for(components):
        extra = ('--no-notify',) if helper_name == 'dark-r-geometry.py' else ()
        run_hook(home, helper_name, Path(relative).name, extra)

def clear_hooks(home=None, restart=True):
    """Remove what the hooks wrote. Each clear is a no-op when it wrote nothing.

    Without restart, running GTK services are left alone, as --no-apply promises.
    """
    for name in ('gtk3.py', 'gtk4-libadwaita.py', 'firefox-chrome.py', 'wallpapers.py'):
        script = ROOT / 'scripts' / name
        if not script.is_file():
            continue
        cmd = [sys.executable, str(script), '--clear']
        if not restart and name.startswith('gtk'):
            cmd.append('--no-restart')
        if home is not None:
            cmd.extend(['--home', str(home)])
        subprocess.run(cmd, check=False)

def apply_theme(components):
    subprocess.run(['omarchy', 'theme', 'set', THEME], check=True)
    # theme-set runs the hooks; call them again so a skipped hook still paints.
    apply_hooks(components)
    if 'bar' in components:
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
    subprocess.run(['hyprctl', 'reload'], check=True)
    check_hyprland()

def managed_source(target, source, stage):
    if target.is_symlink():
        raise RuntimeError('Refusing to replace symlink: ' + str(target))
    if '/plugins/' in str(target):
        plugin = source / 'plugins' / target.name
        if not plugin.exists():
            return None
        return plugin
    staged = stage / target.name
    if target.name in MANAGED_HOOK_NAMES and staged.exists():
        return staged
    raise RuntimeError('No source for managed path: ' + str(target))

def migrate_retired_widgets(shell, record):
    """Put the stock widget back where a retired Dark-R copy stands.

    Each entry keeps its settings and position. The placement record follows,
    so uninstall still restores the original order.
    """
    d = copy.deepcopy(shell)
    layout = d.get('bar', {}).get('layout', {})
    renamed = {}
    for entries in layout.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get('id') in RETIRED_PLUGINS:
                before = replaced_entry(entry['id'], record)
                renamed[entry['id']] = before['id']
                entry['id'] = before['id']
    cluster = (record.get('bar_place') or {}).get('cluster')
    if isinstance(cluster, dict):
        for name, ids in cluster.items():
            cluster[name] = [('omarchy.' + i.split('.', 1)[1]) if i in RETIRED_PLUGINS else i for i in ids]
    if d.get('bar', {}).get('centerAnchor') in renamed:
        d['bar']['centerAnchor'] = renamed[d['bar']['centerAnchor']]
    return d, sorted(renamed)

def describe(target, action):
    return f'{action:<8} {target}'

def install(home, source=None, theme_only=False, apply=True, omarchy_path=None, reinstall=False, components=None, dry_run=False):
    source = ROOT if source is None else Path(source)
    config, state = paths(home)
    record_file = state / 'install.json'
    if record_file.exists():
        if not reinstall:
            raise RuntimeError('Dark-R is already installed by this installer. Uninstall before installing another version, or reinstall with --reinstall.')
        return refresh(home, source, apply, dry_run=dry_run)
    if reinstall:
        raise RuntimeError('No managed Dark-R installation found.')
    if components is None:
        components = LIGHT_COMPONENTS if theme_only else COMPONENTS
    components = parse_components(components)
    if not components:
        raise ValueError('Choose at least one component: ' + ', '.join(COMPONENTS) + '.')
    bar = 'bar' in components
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    if bar and not (omarchy_path / 'shell/Ui/PluginBarApi.qml').exists():
        raise RuntimeError('The bar component requires the Omarchy 4 Quickshell shell. Install without it, for example: ./install.sh gtk firefox wallpapers')
    shell_file = config / 'shell.json'
    before = json.loads(shell_file.read_text()) if shell_file.exists() else None
    if bar and before is None:
        raise RuntimeError('No existing shell.json. Start Omarchy once before installing widgets.')
    after, replaced, placement = patch_shell(before) if bar else (before, {}, {})
    previous = home / '.local/state/omarchy/current/theme.name'
    previous_theme = previous.read_text().strip() if previous.exists() else ''
    if apply and not dry_run and not previous_theme:
        raise RuntimeError('Cannot determine the current theme for rollback. Start Omarchy first.')
    require_theme_checkout(home, source)
    if dry_run:
        lines = ['Components: ' + ' '.join(components)]
        targets = (plugin_targets(config, source) if bar else []) + hook_targets(config, Path('stage'), components)
        for _, target in targets:
            if '/plugins/' in str(target) and target.exists():
                raise RuntimeError('Plugin already exists; refusing to overwrite: ' + str(target))
            lines.append(describe(target, 'replace' if target.exists() else 'create'))
        if bar:
            lines.append(describe(shell_file, 'change') + '  (' + ', '.join(sorted(replaced)) + ', dark-r.stars, dark-r.plate)')
        look = home / '.config/hypr/looknfeel.lua'
        lines.append(describe(look, 'change' if look.exists() else 'create') + '  (Dark-R geometry block)')
        lines.append(describe(state, 'create') + '  (install record and backups)')
        return {'dry_run': lines}
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = state / 'backups' / stamp
    stage = state / ('stage-' + stamp)
    stage.mkdir(parents=True)
    try:
        stage_hooks(stage, source, components)
        targets = plugin_targets(config, source) if bar else []
        targets.extend(hook_targets(config, stage, components))
        for _, target in targets:
            if target.is_symlink():
                raise RuntimeError('Refusing to replace symlink: ' + str(target))
            digest(target)  # Read the tree before mutation. Nested symlinks are hashed, not followed.
            if '/plugins/' in str(target) and target.exists():
                raise RuntimeError('Plugin already exists; refusing to overwrite: ' + str(target))
        if bar and shell_file.is_symlink() and not Path(os.path.realpath(shell_file)).is_file():
            raise RuntimeError('Refusing to replace a symlinked shell.json.')
        backup.mkdir(parents=True)
        record = {'version': 2, 'components': components, 'source_digest': common.source_digest(source),
                  'previous_theme': previous_theme, 'before_shell': before, 'replaced': replaced,
                  'bar_place': placement, 'theme_checkout': True, 'backup': str(backup), 'targets': []}
        if before is not None:
            write_json(backup / 'shell.json', before)
        geometry = None
        try:
            for index, (src, target) in enumerate(targets):
                saved = backup / str(index)
                if target.exists():
                    copy_path(target, saved)
                entry = {'path': str(target), 'saved': str(saved) if saved.exists() else None}
                record['targets'].append(entry)
                remove(target)
                copy_path(src, target)
                entry['digest'] = digest(target)
            if bar:
                write_json(shell_file, after)
            geometry = apply_geometry(home)
            record['geometry_created_looknfeel'] = geometry[1]
            write_json(record_file, record)
            if apply:
                apply_theme(components)
        except Exception:
            for entry in reversed(record['targets']):
                target = Path(entry['path'])
                remove(target)
                if entry['saved']:
                    copy_path(Path(entry['saved']), target)
            if before is not None:
                write_json(shell_file, before)
            if geometry is not None:
                restore_geometry(home, geometry)
            record_file.unlink(missing_ok=True)
            if apply and previous_theme:
                subprocess.run(['omarchy', 'theme', 'set', previous_theme], check=False)
                subprocess.run(['omarchy', 'restart', 'shell'], check=False)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return record

def refresh(home, source, apply, dry_run=False):
    """Replace managed plugin and hook files from this checkout, then apply Dark-R.

    Shell layout and the components chosen at first install stay as they are,
    including the clock format. The Dark-R clock draws its own label. A managed
    file whose contents differ from the install record stops the refresh.
    Files an earlier Dark-R installed and this one retired are removed, and a
    retired bar widget gives its place back to the stock widget.
    """
    state = paths(home)[1]
    record_file = state / 'install.json'
    record_text = record_file.read_text()
    record = load_record(record_file)
    components = record['components']
    bar = 'bar' in components
    config = paths(home)[0]
    require_theme_checkout(home, source)
    record['theme_checkout'] = True
    record['targets'] = without_theme_target(record['targets'], config)
    shell_file = config / 'shell.json'
    shell_before = json.loads(shell_file.read_text()) if bar and shell_file.exists() else None
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    # A dry run stages in a temporary directory so the state stays untouched.
    stage = Path(tempfile.mkdtemp(prefix='dark-r-stage-')) if dry_run else state / ('stage-' + stamp)
    snapshot = state / ('reinstall-' + stamp)
    stage.mkdir(parents=True, exist_ok=True)
    replaced = []
    geometry = None
    shell_written = False
    try:
        stage_hooks(stage, source, components)
        existing_paths = {entry['path'] for entry in record['targets']}
        # Hooks and plugins added after the install record was written still
        # have to be copied. A hot reload does not rebuild bar widgets on screen.
        wanted = hook_targets(config, stage, components) + (plugin_targets(config, source) if bar else [])
        for _src, target in wanted:
            if str(target) not in existing_paths:
                record['targets'].append({'path': str(target), 'saved': None, 'digest': None})
                existing_paths.add(str(target))
        plan = []
        for entry in record['targets']:
            target = Path(entry['path'])
            if target.is_symlink():
                raise RuntimeError('Refusing to replace symlink: ' + str(target))
            if is_retired(target):
                if entry.get('digest') is not None and locally_edited(target, entry.get('digest')):
                    raise RuntimeError('A managed file has local edits. Back up and restore it before reinstalling: ' + str(target))
                plan.append((entry, target, None))
                continue
            src = managed_source(target, source, stage)
            if src is None:
                if target.exists():
                    raise RuntimeError('No source for managed path: ' + str(target))
                continue
            if entry.get('digest') is not None and locally_edited(target, entry.get('digest'), src):
                raise RuntimeError('A managed file has local edits. Back up and restore it before reinstalling: ' + str(target))
            plan.append((entry, target, src))
        shell_after, renamed = migrate_retired_widgets(shell_before, record) if shell_before is not None else (None, [])
        if dry_run:
            lines = ['Components: ' + ' '.join(components)]
            for _entry, target, src in plan:
                lines.append(describe(target, 'remove' if src is None else ('replace' if target.exists() else 'create')))
            if renamed:
                lines.append(describe(shell_file, 'change') + '  (stock widgets return for ' + ', '.join(renamed) + ')')
            look = home / '.config/hypr/looknfeel.lua'
            lines.append(describe(look, 'change' if look.exists() else 'create') + '  (Dark-R geometry block)')
            return {'dry_run': lines}
        snapshot.mkdir()
        for index, (entry, target, src) in enumerate(plan):
            snap = snapshot / str(index)
            if target.exists():
                copy_path(target, snap)
            if is_theme_checkout(target):
                raise RuntimeError('Refusing to replace the theme checkout: ' + str(target))
            remove(target)
            replaced.append(index)
            if src is None:
                if entry.get('saved') and Path(entry['saved']).exists():
                    copy_path(Path(entry['saved']), target)
                continue
            copy_path(src, target)
            restore_symlinks(snap, target)
            entry['digest'] = digest(target)
        record['targets'] = [entry for entry, _target, src in plan if src is not None]
        if renamed:
            write_json(shell_file, shell_after)
            shell_written = True
        geometry = apply_geometry(home)
        if geometry[1]:
            record['geometry_created_looknfeel'] = True
        elif 'geometry_created_looknfeel' not in record:
            record['geometry_created_looknfeel'] = False
        record['source_digest'] = common.source_digest(source)
        write_json(record_file, record)
        if apply:
            apply_theme(components)
    except Exception:
        for index in reversed(replaced):
            target = plan[index][1]
            snap = snapshot / str(index)
            remove(target)
            if snap.exists():
                copy_path(snap, target)
        if shell_written:
            write_json(shell_file, shell_before)
        if geometry is not None:
            restore_geometry(home, geometry)
        if replaced or geometry is not None:
            record_file.write_text(record_text)
            if apply:
                subprocess.run(['omarchy', 'theme', 'set', THEME], check=False)
                if bar:
                    subprocess.run(['omarchy', 'restart', 'shell'], check=False)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(snapshot, ignore_errors=True)
    return record

def uninstall(home, apply=True, source=None, dry_run=False):
    source = ROOT if source is None else Path(source)
    config, state = paths(home)
    record_file = state / 'install.json'
    if not record_file.exists():
        raise RuntimeError('No managed Dark-R installation found.')
    record = load_record(record_file)
    bar = 'bar' in record['components']
    # Only a hand edit of a copied plugin or hook stops uninstall. The checkout
    # stays, and Dark-R stays the selected theme.
    require_theme_checkout(home, source)
    record['theme_checkout'] = True
    targets = without_theme_target(record['targets'], config)
    stage = Path(tempfile.mkdtemp(prefix='dark-r-uninstall-check-'))
    try:
        stage_hooks(stage, source, COMPONENTS)
        for entry in targets:
            target = Path(entry['path'])
            incoming = None
            if not target.is_symlink():
                try:
                    incoming = managed_source(target, source, stage)
                except RuntimeError:
                    incoming = None
            if locally_edited(target, entry.get('digest'), incoming):
                raise RuntimeError('A managed file has local edits. Back up and restore it before uninstalling: ' + str(target))
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    shell_file = config / 'shell.json'
    if dry_run:
        lines = ['Components: ' + ' '.join(record['components'])]
        for entry in reversed(targets):
            lines.append(describe(Path(entry['path']), 'restore' if entry['saved'] else 'remove'))
        if bar:
            lines.append(describe(shell_file, 'change') + '  (stock widgets and order return)')
        lines.append(describe(home / '.config/hypr/looknfeel.lua', 'change') + '  (Dark-R geometry block removed)')
        lines.append('Backups stay in ' + record['backup'])
        return {'dry_run': lines}
    current = json.loads(shell_file.read_text()) if shell_file.exists() else {}
    if bar:
        write_json(shell_file, unpatch_shell(current, record, stock_clock_format()))
    for entry in reversed(targets):
        target = Path(entry['path'])
        if is_theme_checkout(target):
            raise RuntimeError('Refusing to remove the theme checkout: ' + str(target))
        remove(target)
        if entry['saved']:
            copy_path(Path(entry['saved']), target)
    remove_geometry(home, created=bool(record.get('geometry_created_looknfeel')))
    clear_hooks(home, restart=apply)
    if apply:
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
        subprocess.run(['hyprctl', 'reload'], check=True)
        check_hyprland()
    record_file.unlink()
    return record

def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='components:\n'
               '  gtk         GTK 3, GTK 4/libadwaita and GIMP colors\n'
               '  firefox     Firefox userChrome.css (turns on toolkit.legacyUserProfileCustomizations.stylesheets)\n'
               '  bar         Dark-R bar widgets in shell.json\n'
               '  wallpapers  pictures from ~/Pictures/Wallpapers as Dark-R wallpapers\n'
               'With no component, all four are installed. Window geometry comes with every install.')
    p.add_argument('components', nargs='*', metavar='component', help='gtk, firefox, bar, wallpapers')
    p.add_argument('--uninstall', action='store_true')
    p.add_argument('--reinstall', action='store_true', help='refresh managed files from this checkout and apply Dark-R again')
    p.add_argument('--light', action='store_true', help='same as: gtk firefox wallpapers (the bar stays as it is)')
    p.add_argument('--theme-only', action='store_true', help='same as --light')
    p.add_argument('--dry-run', action='store_true', help='list the files that would change, and change nothing')
    p.add_argument('--no-apply', action='store_true', help='install files without reloading the live desktop')
    args = p.parse_args(argv)
    if os.geteuid() == 0:
        p.error('Run as your desktop user, without sudo.')
    light = args.light or args.theme_only
    if args.reinstall and args.uninstall:
        p.error('--reinstall cannot be combined with --uninstall.')
    if (args.reinstall or args.uninstall) and (light or args.components):
        p.error('--reinstall and --uninstall keep the components of the first install. Uninstall first to change them.')
    if light and args.components:
        p.error('--light already chooses the components: gtk firefox wallpapers.')
    try:
        components = parse_components(args.components) if args.components else (list(LIGHT_COMPONENTS) if light else list(COMPONENTS))
        if args.uninstall:
            record = uninstall(Path.home(), apply=not args.no_apply, dry_run=args.dry_run)
        else:
            record = install(Path.home(), components=components, apply=not args.no_apply,
                             reinstall=args.reinstall, dry_run=args.dry_run)
        if args.dry_run:
            print('Dark-R dry run. Nothing was changed.')
            print('\n'.join(record['dry_run']))
        elif args.uninstall:
            print('Dark-R extensions removed. The theme checkout was left in place. Backup retained:', record['backup'])
        elif args.reinstall:
            print('Dark-R extensions reinstalled:', ' '.join(record['components']) + '. The theme checkout was left in place.')
        else:
            print('Dark-R extensions installed:', ' '.join(record['components']) + '. Backup:', record['backup'])
            if 'bar' in record['components']:
                print('Existing custom widgets were preserved.')
            print('Restart applications if they do not live-reload their theme.')
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('Dark-R:', exc, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
