import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage', ROOT/'scripts/manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sys.path.insert(0, str(ROOT/'scripts'))
import dark_r_common as common  # noqa: E402

BASE = {'version': 1, 'idle': {'lock': 420}, 'plugins': [{'id': 'personal.lock'}],
        'bar': {'position': 'top', 'centerAnchor': 'omarchy.clock', 'layout': {
            'left': [{'id': 'omarchy.menu'}, {'id': 'omarchy.workspaces'}, {'id': 'personal.chat'}],
            'center': [{'id': 'omarchy.clock', 'format': 'HH:mm', 'timezone': 'Europe/Zurich'}],
            'right': [{'id': 'omarchy.audio'}, {'id': 'personal.agent', 'color': 'green'}]}}}

class Installation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'user'
        self.shell = self.home/'.config/omarchy/shell.json'
        m.write_json(self.shell, BASE)
        self.current = self.home/'.local/state/omarchy/current/theme.name'
        self.current.parent.mkdir(parents=True)
        self.current.write_text('nord\n')
        self.platform = Path(self.tmp.name)/'platform'
        marker = self.platform/'shell/Ui/PluginBarApi.qml'
        marker.parent.mkdir(parents=True)
        marker.write_text('supported')
    def install(self, **kwargs):
        kwargs.setdefault('source', self.source_copy())
        return m.install(self.home, apply=False, omarchy_path=self.platform, **kwargs)
    def uninstall(self, **kwargs):
        kwargs.setdefault('source', self.source_copy())
        kwargs.setdefault('apply', False)
        return m.uninstall(self.home, **kwargs)
    def source_copy(self):
        # The installer only runs when this directory is the theme checkout.
        theme = self.home/'.config/omarchy/themes/dark-r'
        if theme.exists() or theme.is_symlink():
            return theme
        theme.mkdir(parents=True)
        (theme/'scripts').mkdir()
        for name in ('colors.toml', 'shell.toml', 'icons.theme'):
            shutil.copy2(ROOT/name, theme/name)
        shutil.copytree(ROOT/'backgrounds', theme/'backgrounds')
        shutil.copytree(ROOT/'plugins', theme/'plugins')
        for script in ('dark_r_common.py', 'gtk3.py', 'gtk4-libadwaita.py', 'firefox-chrome.py', 'wallpapers.py', 'geometry.py'):
            shutil.copy2(ROOT/'scripts'/script, theme/'scripts'/script)
        (theme/'.git').mkdir()
        return theme
    def assert_gtk4_hooks(self):
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh'
        helper = self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py'
        self.assertTrue(helper.is_file())
        self.assertIn('dark-r-gtk4-libadwaita.py', hook.read_text())
        self.assertTrue(hook.is_file())
    def assert_always_hooks(self):
        # Every install ships the geometry hook and the module the hooks share.
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-geometry.sh'
        self.assertIn('dark-r-geometry.py', hook.read_text())
        self.assertTrue((self.home/'.config/omarchy/hooks/dark-r-geometry.py').is_file())
        self.assertTrue((self.home/'.config/omarchy/hooks/dark_r_common.py').is_file())
        # Omarchy uses the theme's own vscode-theme.json; there is no VS Code hook.
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py').exists())
    def test_gtk4_hooks_install_with_theme_only(self):
        self.install(theme_only=True)
        self.assert_gtk4_hooks()
        self.assert_always_hooks()
        self.uninstall()
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-geometry.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark_r_common.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-firefox.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-firefox-chrome.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-gtk3.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-wallpapers.sh').exists())
    def test_wallpaper_hook_installs(self):
        self.install(theme_only=True)
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-wallpapers.sh'
        self.assertIn('dark-r-wallpapers.py', hook.read_text())
        self.assertTrue((self.home/'.config/omarchy/hooks/dark-r-wallpapers.py').is_file())
        self.uninstall()
        self.assertFalse(hook.exists())
    def test_install_sets_window_rounding(self):
        look = self.home/'.config/hypr/looknfeel.lua'
        look.parent.mkdir(parents=True)
        original = 'hl.config({ general = { gaps_in = 2 } })\n'
        look.write_text(original)
        self.install()
        text = look.read_text()
        self.assertIn('rounding = 10', text)
        self.assertIn('gaps_in = 2', text)
        self.assertIn('gaps_out = 8', text)
        self.assertIn('border_size = 1', text)
        self.assertIn('shadow = { enabled = false }', text)
        self.assertEqual(text.count('BEGIN Dark-R geometry'), 1)
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        self.assertFalse(record['geometry_created_looknfeel'])
        self.install(reinstall=True)
        self.assertEqual(look.read_text().count('BEGIN Dark-R geometry'), 1)
        self.assertIn('gaps_in = 2', look.read_text())
        self.uninstall()
        self.assertEqual(look.read_text(), original)
    def test_install_follows_looknfeel_symlink(self):
        real = self.home/'.dotfiles/config/hypr/looknfeel.lua'
        real.parent.mkdir(parents=True)
        original = 'hl.config({ general = { gaps_in = 2 } })\n'
        real.write_text(original)
        link = self.home/'.config/hypr/looknfeel.lua'
        link.parent.mkdir(parents=True)
        link.symlink_to(real)
        self.install()
        self.assertTrue(link.is_symlink())
        self.assertIn('rounding = 10', real.read_text())
        self.assertIn('gaps_in = 2', real.read_text())
        self.uninstall()
        self.assertEqual(real.read_text(), original)
        self.assertTrue(link.is_symlink())
    def test_light_install_creates_rounding_file(self):
        self.install(theme_only=True)
        look = self.home/'.config/hypr/looknfeel.lua'
        self.assertIn('rounding = 10', look.read_text())
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        self.assertTrue(record['geometry_created_looknfeel'])
        self.uninstall()
        self.assertFalse(look.exists())
    def test_gtk3_hook_installs(self):
        self.install(theme_only=True)
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk3.sh'
        self.assertIn('dark-r-gtk3.py', hook.read_text())
        self.assertTrue((self.home/'.config/omarchy/hooks/dark-r-gtk3.py').is_file())
    def test_reinstall_adds_gtk4_hooks_to_old_record(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        record['targets'] = [entry for entry in record['targets'] if 'gtk4' not in entry['path']]
        for path in [
            self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py',
            self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh',
        ]:
            if path.exists():
                path.unlink()
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assert_gtk4_hooks()
        self.assert_always_hooks()
        saved = json.loads(record_path.read_text())
        self.assertTrue(any(entry['path'].endswith('dark-r-gtk4-libadwaita.py') for entry in saved['targets']))
        self.assertTrue(any(entry['path'].endswith('dark-r-gtk4.sh') for entry in saved['targets']))
        self.assertFalse(any('vscode' in entry['path'] for entry in saved['targets']))
        self.assertTrue(any(entry['path'].endswith('dark-r-geometry.sh') for entry in saved['targets']))
    def test_reinstall_copies_plugins_missing_from_old_record(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        record['targets'] = [entry for entry in record['targets'] if not entry['path'].endswith('/dark-r.plate')]
        record_path.write_text(json.dumps(record))
        plate = self.home/'.config/omarchy/plugins/dark-r.plate/Plate.qml'
        plate.write_text('// stale\n')
        self.install(source=source, reinstall=True)
        self.assertIn('plateColor', plate.read_text())
        saved = json.loads(record_path.read_text())
        self.assertTrue(any(entry['path'].endswith('/dark-r.plate') for entry in saved['targets']))
    def test_gtk4_palette_generator(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('gtk4', ROOT/'scripts'/'gtk4-libadwaita.py')
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        css = g.build_css(g.load_colors(ROOT/'colors.toml'))
        # Chosen and checked are green. Amber is only hover and warn.
        self.assertIn('@define-color accent_bg_color #77af8a;', css)
        self.assertIn('@define-color accent_color #77af8a;', css)
        self.assertIn('--window-bg-color: #0c040f;', css)
        self.assertIn('--view-bg-color: #0c040f;', css)
        self.assertIn('--accent-fg-color: #0c040f;', css)
        self.assertIn('--accent-color: #77af8a;', css)
        self.assertIn('--accent-bg-color: #77af8a;', css)
        self.assertNotIn('oklab(', css)
        self.assertIn('--headerbar-bg-color: #3f2c53;', css)
        self.assertIn('--card-bg-color: #181820;', css)
        self.assertIn('--sidebar-bg-color: #181820;', css)
        self.assertIn('--popover-bg-color: #181820;', css)
        self.assertIn('--headerbar-border-color: #9385a5;', css)
        self.assertIn('--warning-bg-color: #f0a202;', css)
        self.assertIn('--success-bg-color: #77af8a;', css)
        # Selection is the inactive border under bright_foreground.
        self.assertIn('@define-color theme_selected_bg_color #3f2c53;', css)
        self.assertIn('@define-color theme_selected_fg_color #fff3e6;', css)
        self.assertIn('@define-color link_color #d2bced;', css)
        self.assertIn('@define-color borders #9385a5;', css)
        # Rules carry the roles the variables cannot.
        self.assertIn('outline-color: #fff3e6;', css)
        self.assertIn('.navigation-sidebar > row:selected', css)
        self.assertNotIn('#a5ace1', css)
        self.assertIn('@define-color insensitive_fg_color #9385a5;', css)
        # Link buttons stay links on hover; destructive stays red.
        self.assertIn(':not(.destructive-action):not(.link),', css)
        self.assertIn('button.destructive-action:hover:not(:disabled) {\n  background-color: #ffa5ad;', css)
        self.assertIn('button.suggested-action:hover:not(:disabled) {\n  background-color: #9add6d;', css)
        home = self.home
        (home/'.local/state/omarchy/current').mkdir(parents=True, exist_ok=True)
        (home/'.local/state/omarchy/current/theme.name').write_text('dark-r\n')
        theme = home/'.local/state/omarchy/current/theme'
        theme.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/'colors.toml', theme/'colors.toml')
        self.assertEqual(g.apply(home, restart=False), 0)
        gtk_css = (home/'.config/gtk-4.0/gtk.css').read_text()
        self.assertIn('omarchy-dark-r.css', gtk_css)
        self.assertIn('#f0a202', (home/'.config/gtk-4.0/omarchy-dark-r.css').read_text())
        (home/'.local/state/omarchy/current/theme.name').write_text('nord\n')
        self.assertEqual(g.apply(home, restart=False), 0)
        self.assertFalse((home/'.config/gtk-4.0/omarchy-dark-r.css').exists())
        self.assertFalse((home/'.config/gtk-4.0/gtk.css').exists())
        # Preserve foreign user CSS around the managed block.
        (home/'.local/state/omarchy/current/theme.name').write_text('dark-r\n')
        (home/'.config/gtk-4.0').mkdir(parents=True, exist_ok=True)
        (home/'.config/gtk-4.0/gtk.css').write_text('/* mine */\nwindow { opacity: 1; }\n')
        self.assertEqual(g.apply(home, restart=False), 0)
        text = (home/'.config/gtk-4.0/gtk.css').read_text()
        self.assertIn('/* mine */', text)
        self.assertIn('BEGIN omarchy-dark-r gtk4', text)
        self.assertEqual(g.apply(home, clear=True, restart=False), 0)
        self.assertEqual((home/'.config/gtk-4.0/gtk.css').read_text(), '/* mine */\nwindow { opacity: 1; }\n')
        self.assertFalse((home/'.config/gtk-4.0/omarchy-dark-r.css').exists())
    def test_vscode_surface_ramp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('vscode', ROOT/'scripts'/'vscode_surfaces.py')
        v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v)
        colors = common.load_colors(ROOT/'colors.toml')
        workbench = v.chrome(colors)
        # Regions: code well on background, chrome on the card, header strip.
        self.assertEqual(workbench['editor.background'], '#0c040f')
        self.assertEqual(workbench['sideBar.background'], '#181820')
        self.assertEqual(workbench['activityBar.background'], '#181820')
        self.assertEqual(workbench['panel.background'], '#181820')
        self.assertEqual(workbench['titleBar.activeBackground'], '#3f2c53')
        self.assertEqual(workbench['tab.activeBackground'], workbench['editor.background'])
        self.assertNotEqual(workbench['tab.activeBackground'], workbench['tab.inactiveBackground'])
        # Separators are quiet; magenta is not a split line.
        self.assertEqual(workbench['editorGroup.border'], '#3f2c53')
        self.assertEqual(workbench['activityBar.border'], '#3f2c53')
        # Current is sage.
        self.assertEqual(workbench['tab.activeForeground'], '#77af8a')
        self.assertEqual(workbench['tab.activeBorderTop'], '#77af8a')
        self.assertEqual(workbench['activityBar.foreground'], '#77af8a')
        self.assertEqual(workbench['list.activeSelectionForeground'], '#77af8a')
        self.assertEqual(workbench['button.background'], '#77af8a')
        # Hover and keyboard rows are solid amber with dark text.
        for key in ('tab.hoverBackground', 'quickInputList.focusBackground', 'menu.selectionBackground',
                    'menubar.selectionBackground', 'editorSuggestWidget.selectedBackground',
                    'statusBarItem.hoverBackground', 'list.focusOutline'):
            self.assertEqual(workbench[key], '#f0a202', key)
        for key in ('tab.hoverForeground', 'quickInputList.focusForeground', 'menu.selectionForeground',
                    'editorSuggestWidget.selectedForeground', 'list.focusHighlightForeground',
                    'editorSuggestWidget.focusHighlightForeground'):
            self.assertEqual(workbench[key], '#0c040f', key)
        # Lists keep amber matches readable, so their fills stay quiet.
        self.assertEqual(workbench['list.highlightForeground'], '#f0a202')
        self.assertEqual(workbench['list.hoverBackground'], '#3f2c53')
        self.assertGreaterEqual(common.contrast(workbench['list.highlightForeground'], workbench['list.hoverBackground']), 4.5)
        self.assertGreaterEqual(common.contrast(workbench['list.activeSelectionForeground'], workbench['list.activeSelectionBackground']), 4.5)
        # Focus, dim, cards, links, notices.
        self.assertEqual(workbench['focusBorder'], '#fff3e6')
        for key in ('input.border', 'dropdown.border', 'checkbox.border', 'editorWidget.border',
                    'notifications.border', 'widget.border', 'descriptionForeground', 'input.placeholderForeground'):
            self.assertEqual(workbench[key], '#9385a5', key)
        self.assertEqual(workbench['textLink.foreground'], '#d2bced')
        self.assertEqual(workbench['textLink.activeForeground'], '#efe3a6')
        self.assertEqual(workbench['editorWarning.foreground'], '#f0a202')
        self.assertEqual(workbench['editorInfo.foreground'], '#a5ace1')
        self.assertEqual(workbench['editorError.foreground'], '#ec8790')
        # Editor selection is the opaque inactive-border fill.
        self.assertEqual(workbench['editor.selectionBackground'], '#3f2c53')
        self.assertGreaterEqual(common.contrast(workbench['editor.selectionBackground'], workbench['editor.background']), 1.5)
        self.assertGreaterEqual(common.contrast('#e0e6e2', workbench['editor.selectionBackground']), 7)
        # No translucent washes for UI hover or selection.
        for key in ('tab.hoverBackground', 'toolbar.hoverBackground', 'list.hoverBackground',
                    'editor.selectionBackground', 'terminal.selectionBackground',
                    'menubar.selectionBackground', 'activityBar.activeBackground', 'list.focusOutline'):
            self.assertEqual(len(workbench[key]), 7, key)
        generated = {
            'name': 'Omarchy',
            'colors': {
                'editor.background': '#0c040f',
                'sideBar.background': '#0c040f',
                'activityBar.background': '#0c040f',
                'panel.background': '#0c040f',
                'tab.activeBackground': '#0c040f',
                'tab.inactiveBackground': '#0c040f',
            },
            'tokenColors': [{'name': 'Comment'}],
        }
        patched = v.patch_theme(generated, colors)
        self.assertEqual(patched['tokenColors'], [{'name': 'Comment'}])
        self.assertEqual(patched['colors']['editor.background'], '#0c040f')
        self.assertEqual(patched['colors']['sideBar.background'], workbench['sideBar.background'])
        self.assertEqual(patched['colors']['activityBar.background'], workbench['activityBar.background'])
        self.assertEqual(patched['colors']['panel.background'], workbench['panel.background'])
        self.assertEqual(patched['colors']['tab.inactiveBackground'], workbench['tab.inactiveBackground'])
        self.assertEqual(patched['colors']['titleBar.activeBackground'], '#3f2c53')
        self.assertEqual(generated['colors']['sideBar.background'], '#0c040f')
    def test_gtk4_restart_spares_processes_with_windows(self):
        g = load_script('gtk4-libadwaita')
        def run(cmd, **kwargs):
            if cmd[:2] == ['hyprctl', 'clients']:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps([{'pid': 101}, {'pid': 7}]), stderr='')
            if cmd[:2] == ['pgrep', '-x']:
                return subprocess.CompletedProcess(cmd, 0, stdout='101\n202\n' if cmd[2] == 'nautilus' else '', stderr='')
            raise AssertionError(cmd)
        with patch.object(g.subprocess, 'run', side_effect=run), patch.object(g.os, 'kill') as kill:
            g.restart_gtk_services()
        kill.assert_called_once_with(202, g.signal.SIGTERM)
        # Without Hyprland nothing is stopped.
        with patch.object(g.subprocess, 'run', side_effect=OSError), patch.object(g.os, 'kill') as kill:
            g.restart_gtk_services()
        kill.assert_not_called()
    def test_no_apply_uninstall_leaves_gtk_services_alone(self):
        self.install(theme_only=True)
        with patch.object(m.subprocess, 'run') as run:
            self.uninstall()
        for call in run.call_args_list:
            cmd = call.args[0]
            if any(str(part).endswith(('gtk3.py', 'gtk4-libadwaita.py')) for part in cmd):
                self.assertIn('--no-restart', cmd)
    def test_chromium_seed(self):
        import colorsys
        import re
        spec = importlib.util.spec_from_file_location('build', ROOT/'scripts'/'build.py')
        b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b)
        text = (ROOT/'chromium.theme').read_text()
        self.assertEqual(text, b.build_chromium(ROOT))
        # The form browser_policy_theme_hex accepts; anything else falls back to #1c2027.
        match = re.fullmatch(r'\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*', text)
        self.assertIsNotNone(match)
        rgb = [int(part) for part in match.groups()]
        self.assertTrue(all(part < 256 for part in rgb))
        self.assertEqual(text, '9,7,12\n')
        # Dark, so Chromium stays in dark mode, with the hue of the Firefox toolbar.
        hue, lightness, _ = colorsys.rgb_to_hls(*(part / 255 for part in rgb))
        bar_hue, _, _ = colorsys.rgb_to_hls(*(int(common.roles(common.load_colors(ROOT/'colors.toml'))['bar'][i:i + 2], 16) / 255 for i in (1, 3, 5)))
        self.assertLess(lightness, 0.06)
        self.assertAlmostEqual(hue, bar_hue, delta=0.02)
    def test_firefox_palette(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('firefox', ROOT/'scripts'/'firefox-chrome.py')
        f = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(f)
        css = f.build_chrome(f.load_colors(ROOT/'colors.toml'))
        self.assertIn('--toolbar-background-color: #3f2c53 !important;', css)
        self.assertIn('--color-accent-primary: #77af8a !important;', css)
        self.assertIn('--link-color: #d2bced !important;', css)
        self.assertIn('--focus-outline-color: #fff3e6 !important;', css)
        self.assertIn('--urlbarview-background-color-selected: #f0a202 !important;', css)
        self.assertIn('--urlbarview-text-color-selected: #0c040f !important;', css)
        # Selected tab is sage; destructive stays red, brighter on hover.
        self.assertIn('--tab-border-color-selected: #77af8a !important;', css)
        self.assertIn('--tab-border-color-selected-leading: #77af8a !important;', css)
        self.assertIn('--tab-border-color-selected-trailing: #77af8a !important;', css)
        self.assertIn('--button-background-color-destructive: #ec8790 !important;', css)
        self.assertIn('--button-background-color-destructive-hover: #ffa5ad !important;', css)
        self.assertIn('--panel-background-color: #181820 !important;', css)
        self.assertNotIn('.tab-background', css)
        home = self.home
        state = home/'.local/state/omarchy/current'
        state.mkdir(parents=True, exist_ok=True)
        (state/'theme.name').write_text('dark-r\n')
        theme = state/'theme'
        theme.mkdir()
        shutil.copy2(ROOT/'colors.toml', theme/'colors.toml')
        profile = home/'.config/mozilla/firefox/abc.default-release'
        profile.mkdir(parents=True)
        webapp = home/'.config/mozilla/firefox/web.WebApps'
        webapp.mkdir()
        (home/'.config/mozilla/firefox/profiles.ini').write_text(
            '[Profile0]\nName=default-release\nIsRelative=1\nPath=abc.default-release\n'
            '\n[Profile1]\nName=WebApps\nIsRelative=1\nPath=web.WebApps\n'
        )
        (profile/'chrome').mkdir()
        (profile/'chrome/userChrome.css').write_text('/* mine */\n#urlbar { opacity: 1; }\n')
        (profile/'user.js').write_text('user_pref("browser.startup.page", 1);\n')
        self.assertEqual(f.apply(home), 0)
        chrome = (profile/'chrome/userChrome.css').read_text()
        self.assertIn('/* mine */', chrome)
        self.assertIn('omarchy-dark-r.css', chrome)
        sheet = (profile/'chrome/omarchy-dark-r.css').read_text()
        self.assertIn('#f0a202', sheet)
        self.assertIn('#3f2c53', sheet)
        self.assertIn('#77af8a', sheet)
        self.assertFalse((webapp/'chrome/omarchy-dark-r.css').exists())
        prefs = (profile/'user.js').read_text()
        self.assertIn('toolkit.legacyUserProfileCustomizations.stylesheets', prefs)
        self.assertIn('browser.startup.page', prefs)
        (state/'theme.name').write_text('nord\n')
        self.assertEqual(f.apply(home), 0)
        self.assertFalse((profile/'chrome/omarchy-dark-r.css').exists())
        self.assertEqual((profile/'chrome/userChrome.css').read_text(), '/* mine */\n#urlbar { opacity: 1; }\n')
        self.assertEqual((profile/'user.js').read_text(), 'user_pref("browser.startup.page", 1);\n')
    def test_round_trip_preserves_unrelated_changes(self):
        self.install()
        self.assert_gtk4_hooks()
        d = json.loads(self.shell.read_text())
        # keep the rest of the original test body by re-reading below marker if needed
        clock = next(x for x in d['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        self.assertEqual(clock['format'], 'HH:mm')
        ids = [x['id'] for x in d['bar']['layout']['right']]
        self.assertIn('dark-r.plate', ids)
        self.assertNotIn('dark-r.band', ids)
        self.assertEqual(d['idle'], BASE['idle'])
        self.assertEqual(d['plugins'], BASE['plugins'])
        self.assertEqual(clock['timezone'], 'Europe/Zurich')
        self.assertEqual(d['bar']['layout']['center'][0]['id'], 'dark-r.workspaces')
        self.assertNotIn('centerAnchor', d['bar'])
        self.assert_always_hooks()
        theme = self.home/'.config/omarchy/themes/dark-r'
        for name in ('alacritty.toml', 'kitty.conf', 'ghostty.conf', 'foot.ini'):
            self.assertFalse((theme/name).exists())  # Omarchy renders these from colors.toml.
        d['idle']['lock'] = 900
        d['bar']['layout']['right'].append({'id': 'new.widget'})
        clock['timezone'] = 'UTC'
        m.write_json(self.shell, d)
        self.uninstall()
        d = json.loads(self.shell.read_text())
        self.assertEqual(d['idle']['lock'], 900)
        self.assertEqual(d['bar']['layout']['right'][-1]['id'], 'new.widget')
        self.assertNotIn('dark-r.plate', [x['id'] for x in d['bar']['layout']['right']])
        self.assertEqual(d['bar']['layout']['center'][0]['id'], 'omarchy.clock')
        self.assertEqual(d['bar']['layout']['center'][0]['format'], 'HH:mm')
        self.assertEqual(d['bar']['layout']['center'][0]['timezone'], 'UTC')
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-vscode-surfaces.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-firefox.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-firefox-chrome.py').exists())
    def test_center_group_stays_beside_the_workspaces(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['centerBegin'] = [{'id': 'personal.before'}]
        d['bar']['layout']['center'] = [
            {'id': 'omarchy.indicators'},
            {'id': 'omarchy.clock', 'format': 'HH:mm', 'timezone': 'Europe/Zurich'},
            {'id': 'omarchy.elsewhen'},
        ]
        d['bar']['layout']['centerEnd'] = [{'id': 'personal.after'}]
        m.write_json(self.shell, d)
        self.install()
        laid = json.loads(self.shell.read_text())['bar']['layout']
        self.assertEqual([x['id'] for x in laid['centerBegin']], ['personal.before', 'dark-r.indicators'])
        self.assertEqual([x['id'] for x in laid['center']], ['dark-r.workspaces'])
        self.assertEqual([x['id'] for x in laid['centerEnd']], ['omarchy.elsewhen', 'personal.after'])
        self.assertEqual(laid['left'][1]['id'], 'dark-r.clock')
        self.assertEqual(laid['left'][1]['format'], 'HH:mm')
        current = json.loads(self.shell.read_text())
        current['bar']['layout']['centerEnd'].append({'id': 'new.widget'})
        m.write_json(self.shell, current)
        self.uninstall()
        restored = json.loads(self.shell.read_text())
        layout = restored['bar']['layout']
        self.assertEqual([x['id'] for x in layout['center']], ['omarchy.indicators', 'omarchy.clock', 'omarchy.elsewhen'])
        self.assertEqual(layout['center'][1]['timezone'], 'Europe/Zurich')
        self.assertEqual([x['id'] for x in layout['left']], ['omarchy.menu', 'omarchy.workspaces', 'personal.chat'])
        self.assertEqual(layout['centerEnd'][-1]['id'], 'new.widget')
        self.assertEqual([x['id'] for x in layout['centerBegin']], ['personal.before'])
        self.assertEqual(restored['bar']['centerAnchor'], 'omarchy.clock')
    def test_uninstall_reverts_widgets_missing_from_record(self):
        # A widget renamed on the bar but absent from the record still goes back.
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'].insert(0, {'id': 'omarchy.indicators', 'size': 2})
        m.write_json(self.shell, d)
        self.install()
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        del record['replaced']['dark-r.indicators']
        record_path.write_text(json.dumps(record))
        self.uninstall()
        layout = json.loads(self.shell.read_text())['bar']['layout']
        self.assertEqual(layout['center'][0], {'id': 'omarchy.indicators', 'size': 2})
        self.assertFalse(any(x['id'].startswith('dark-r.') for entries in layout.values() for x in entries))
    def test_uninstall_twice_keeps_the_restored_bar(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'] = [
            {'id': 'omarchy.indicators'},
            {'id': 'omarchy.clock', 'format': 'HH:mm'},
            {'id': 'omarchy.elsewhen'},
            {'id': 'personal.music'},
        ]
        m.write_json(self.shell, d)
        self.install()
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        once = m.unpatch_shell(json.loads(self.shell.read_text()), record)
        self.assertEqual([x['id'] for x in once['bar']['layout']['center']],
                         ['omarchy.indicators', 'omarchy.clock', 'omarchy.elsewhen', 'personal.music'])
        self.assertEqual(m.unpatch_shell(once, record), once)
    def test_clock_format_survives_install_and_uninstall_twice(self):
        for _ in range(2):
            self.install()
            clock = next(x for x in json.loads(self.shell.read_text())['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
            self.assertEqual(clock['format'], 'HH:mm')
            self.uninstall()
            clock = json.loads(self.shell.read_text())['bar']['layout']['center'][0]
            self.assertEqual((clock['id'], clock['format'], clock['timezone']), ('omarchy.clock', 'HH:mm', 'Europe/Zurich'))
            self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.clock').exists())
    def test_uninstall_accepts_a_plugin_that_matches_this_checkout(self):
        source = self.source_copy()
        self.install(source=source)
        plugin = self.home/'.config/omarchy/plugins/dark-r.clock/Model.js'
        plugin.write_text(plugin.read_text() + '\n// shipped from this checkout\n')
        shutil.copy2(plugin, source/'plugins/dark-r.clock/Model.js')
        self.uninstall(source=source)
        clock = json.loads(self.shell.read_text())['bar']['layout']['center'][0]
        self.assertEqual((clock['id'], clock['format']), ('omarchy.clock', 'HH:mm'))
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
    def test_install_leaves_the_clock_format(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'][0]['format'] = 'HH:mm:ss'
        m.write_json(self.shell, d)
        self.install()
        clock = next(x for x in json.loads(self.shell.read_text())['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        self.assertEqual(clock['format'], 'HH:mm:ss')
        self.assertEqual(clock['timezone'], 'Europe/Zurich')
        self.uninstall()
        clock = json.loads(self.shell.read_text())['bar']['layout']['center'][0]
        self.assertEqual((clock['id'], clock['format']), ('omarchy.clock', 'HH:mm:ss'))
    def test_uninstall_resets_theme_clock_formats(self):
        for before, expected in (('HH:mm', 'HH:mm'), ('yyyyMM.dd ddd HH:mm', 'dddd HH:mm')):
            with self.subTest(before=before):
                self.setUp()
                d = copy.deepcopy(BASE)
                d['bar']['layout']['center'][0]['format'] = before
                m.write_json(self.shell, d)
                self.install()
                current = json.loads(self.shell.read_text())
                clock = next(x for x in current['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
                clock['format'] = 'yyyyMM.dd ddd HH:mm'
                m.write_json(self.shell, current)
                with patch.dict(os.environ, {'OMARCHY_PATH': str(self.platform)}):
                    self.uninstall()
                clock = json.loads(self.shell.read_text())['bar']['layout']['center'][0]
                self.assertEqual((clock['id'], clock['format']), ('omarchy.clock', expected))
                self.tearDown()
    def test_stock_clock_format_comes_from_omarchy(self):
        stock = self.platform/'config/omarchy/shell.json'
        stock.parent.mkdir(parents=True)
        stock.write_text(json.dumps({'bar': {'layout': {'center': [{'id': 'omarchy.clock', 'format': 'ddd HH:mm'}]}}}))
        self.assertEqual(m.stock_clock_format(self.platform), 'ddd HH:mm')
        stock.unlink()
        self.assertEqual(m.stock_clock_format(self.platform), m.STOCK_CLOCK_FORMAT)
    def test_custom_clones_are_preserved(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'][0]['id'] = 'custom.clock'
        d['bar']['centerAnchor'] = 'custom.clock'
        m.write_json(self.shell, d)
        self.install()
        after = json.loads(self.shell.read_text())
        self.assertEqual(after['bar']['layout']['center'], d['bar']['layout']['center'])
        self.assertEqual(after['bar']['centerAnchor'], 'custom.clock')
    def test_checkout_file_is_left_alone(self):
        theme = self.source_copy()
        p = theme/'mine.txt'
        p.write_text('personal palette')
        self.install()
        self.uninstall()
        self.assertEqual(p.read_text(), 'personal palette')
        self.assertTrue((theme/'.git').is_dir())
    def test_reinstall_refuses_before_changes(self):
        self.install()
        before = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(before, self.shell.read_bytes())
    def test_reinstall_refreshes_plugins_without_touching_the_checkout(self):
        source = self.source_copy()
        personal = source/'mine.txt'
        personal.write_text('personal palette')
        self.install(source=source)
        shell = json.loads(self.shell.read_text())
        shell['idle']['lock'] = 900
        m.write_json(self.shell, shell)
        qml = source/'plugins/dark-r.stars/Stars.qml'
        qml.write_text(qml.read_text() + '\n// trail\n')
        record = self.install(source=source, reinstall=True)
        self.assertFalse(any(entry['path'].endswith('/themes/dark-r') for entry in record['targets']))
        self.assertEqual(personal.read_text(), 'personal palette')
        self.assertIn('// trail', (self.home/'.config/omarchy/plugins/dark-r.stars/Stars.qml').read_text())
        restored = json.loads(self.shell.read_text())
        self.assertEqual(restored['idle']['lock'], 900)
        self.assertEqual([x['id'] for x in restored['bar']['layout']['right']].count('dark-r.plate'), 1)
        self.assertEqual([x['id'] for x in restored['bar']['layout']['left']].count('dark-r.stars'), 1)
        self.uninstall()
        self.assertEqual(personal.read_text(), 'personal palette')
    def test_reinstall_leaves_the_clock_format(self):
        source = self.source_copy()
        self.install(source=source)
        shell = json.loads(self.shell.read_text())
        clock = next(x for x in shell['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        clock['format'] = 'HH:mm'
        shell['idle']['lock'] = 900
        m.write_json(self.shell, shell)
        self.install(source=source, reinstall=True)
        restored = json.loads(self.shell.read_text())
        clock = next(x for x in restored['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        self.assertEqual(clock['format'], 'HH:mm')
        self.assertEqual(clock['timezone'], 'Europe/Zurich')
        self.assertEqual(restored['idle']['lock'], 900)
    def test_reinstall_keeps_a_clock_label_chosen_later(self):
        source = self.source_copy()
        self.install(source=source)
        shell = json.loads(self.shell.read_text())
        clock = next(x for x in shell['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        clock['format'] = 'HH:mm:ss'
        m.write_json(self.shell, shell)
        self.install(source=source, reinstall=True)
        clock = next(x for x in json.loads(self.shell.read_text())['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        self.assertEqual(clock['format'], 'HH:mm:ss')
    def test_reinstall_leaves_files_in_the_checkout(self):
        source = self.source_copy()
        self.install(source=source)
        foot = source/'foot.ini'
        foot.write_text('[colors-dark]\nalpha=0.85\n')
        self.install(source=source, reinstall=True)
        self.assertEqual(foot.read_text(), '[colors-dark]\nalpha=0.85\n')
        self.assertTrue((source/'.git').is_dir())
    def test_reinstall_keeps_theme_only(self):
        source = self.source_copy()
        self.install(source=source, theme_only=True)
        self.install(source=source, reinstall=True)
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
    def test_reinstall_refuses_local_edits(self):
        source = self.source_copy()
        self.install(source=source)
        plugin = self.home/'.config/omarchy/plugins/dark-r.stars/Stars.qml'
        plugin.write_text(plugin.read_text() + '\n// mine\n')
        edited = plugin.read_text()
        shell = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): self.install(source=source, reinstall=True)
        self.assertEqual(plugin.read_text(), edited)
        self.assertEqual(self.shell.read_bytes(), shell)
    def test_reinstall_without_install_does_nothing(self):
        with self.assertRaises(RuntimeError): self.install(reinstall=True)
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_reinstall_apply_failure_restores_files(self):
        source = self.source_copy()
        self.install(source=source)
        installed = self.home/'.config/omarchy/plugins/dark-r.stars/Stars.qml'
        before_plugin = installed.read_text()
        before_record = (self.home/'.local/state/omarchy-dark-r/install.json').read_text()
        (source/'plugins/dark-r.stars/Stars.qml').write_text(before_plugin + '\n// next\n')
        with patch.object(m.subprocess, 'run', side_effect=[subprocess.CalledProcessError(1, 'omarchy'), None, None]):
            with self.assertRaises(subprocess.CalledProcessError):
                m.install(self.home, source=source, apply=True, omarchy_path=self.platform, reinstall=True)
        self.assertEqual(installed.read_text(), before_plugin)
        self.assertEqual((self.home/'.local/state/omarchy-dark-r/install.json').read_text(), before_record)
        self.assertFalse(any(self.home.joinpath('.local/state/omarchy-dark-r').glob('reinstall-*')))
        self.assertFalse(any(self.home.joinpath('.local/state/omarchy-dark-r').glob('stage-*')))
    def test_reinstall_flag_rejects_option_changes(self):
        for flag in ('--theme-only', '--light'):
            with self.subTest(flag=flag):
                with patch.object(sys, 'argv', ['manage.py', '--reinstall', flag]), patch('sys.stderr', io.StringIO()):
                    with self.assertRaises(SystemExit):
                        m.main()
    def test_light_flag_installs_without_touching_the_bar(self):
        theme = self.source_copy()
        with patch.object(sys, 'argv', ['manage.py', '--light', '--no-apply']), \
             patch.object(m.Path, 'home', return_value=self.home), \
             patch.object(m, 'ROOT', theme), \
             patch('sys.stdout', io.StringIO()) as out:
            self.assertEqual(m.main(), 0)
        self.assertIn('gtk firefox wallpapers', out.getvalue())
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
        self.assertTrue((self.home/'.config/omarchy/themes/dark-r/shell.toml').is_file())
        self.assert_gtk4_hooks()
        self.assert_always_hooks()
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        self.assertEqual(record['components'], ['gtk', 'firefox', 'wallpapers'])
    def test_conflicting_plugin_is_not_overwritten(self):
        p = self.home/'.config/omarchy/plugins/dark-r.stars/mine.qml'
        p.parent.mkdir(parents=True)
        p.write_text('personal')
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(p.read_text(), 'personal')
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_install_ships_hidden_stars(self):
        self.install()
        d = json.loads(self.shell.read_text())
        self.assertIn({'id': 'dark-r.stars', 'shown': False}, d['bar']['layout']['left'])
        self.assertTrue((self.home/'.config/omarchy/plugins/dark-r.stars').is_dir())
        self.assertIn('dark-r.plate', [x['id'] for x in d['bar']['layout']['right']])
        # omarchy theme set drops every .lua file from a cloned theme and warns
        # about it, so the theme ships none. Geometry comes from the installer.
        self.assertEqual(list(ROOT.glob('*.lua')), [])
    def test_theme_only_does_not_change_shell(self):
        before = self.shell.read_bytes()
        self.install(theme_only=True)
        self.assertEqual(before, self.shell.read_bytes())
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
        self.uninstall()
        self.assertEqual(before, self.shell.read_bytes())
    def test_local_edits_block_destructive_uninstall(self):
        self.install()
        p = self.home/'.config/omarchy/plugins/dark-r.stars/Stars.qml'
        p.write_text(p.read_text()+'\n// my edit\n')
        before = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): self.uninstall()
        self.assertEqual(before, self.shell.read_bytes())
        self.assertIn('// my edit', p.read_text())
    def test_apply_failure_rolls_back(self):
        source = self.source_copy()
        with patch.object(m.subprocess, 'run') as run:
            run.side_effect = [subprocess.CalledProcessError(1, 'omarchy'), None, None]
            with self.assertRaises(subprocess.CalledProcessError):
                m.install(self.home, source=source, apply=True, omarchy_path=self.platform)
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
        self.assertTrue((source/'.git').is_dir())
        self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.clock').exists())
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
    def test_vertical_bar_rejected_without_changes(self):
        d = copy.deepcopy(BASE);d['bar']['position'] = 'left'
        m.write_json(self.shell, d)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(json.loads(self.shell.read_text()), d)
    def test_reinstall_skips_plugins_removed_from_source(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        ghost = self.home/'.config/omarchy/plugins/dark-r.audio'
        record['targets'].append({'path': str(ghost), 'saved': None, 'digest': 'gone'})
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assertFalse(ghost.exists())
        saved = json.loads(record_path.read_text())
        self.assertFalse(any(entry['path'].endswith('dark-r.audio') for entry in saved['targets']))
    def place_checkout(self):
        theme = self.source_copy()
        (theme/'README.md').write_text('keep\n')
        return theme
    def test_theme_checkout_installs_extensions_only(self):
        theme = self.place_checkout()
        colors = (theme/'colors.toml').read_bytes()
        record = self.install(source=theme)
        self.assertTrue(record['theme_checkout'])
        self.assertFalse(any(entry['path'].endswith('/themes/dark-r') for entry in record['targets']))
        self.assertEqual((theme/'colors.toml').read_bytes(), colors)
        self.assertTrue((theme/'.git').is_dir())
        self.assertEqual((theme/'README.md').read_text(), 'keep\n')
        self.assertTrue((theme/'plugins/dark-r.workspaces').is_dir())
        self.assertTrue((self.home/'.config/omarchy/plugins/dark-r.workspaces').is_dir())
        self.assert_gtk4_hooks()
    def test_theme_checkout_light_leaves_the_bar(self):
        theme = self.place_checkout()
        before = self.shell.read_text()
        record = self.install(source=theme, theme_only=True)
        self.assertTrue(record['theme_checkout'])
        self.assertEqual(self.shell.read_text(), before)
        self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.workspaces').exists())
        self.assert_gtk4_hooks()
        self.assertTrue((theme/'.git').is_dir())
    def test_gitdir_file_counts_as_a_checkout(self):
        theme = self.place_checkout()
        (theme/'.git').rmdir()
        (theme/'.git').write_text('gitdir: /somewhere\n')
        record = self.install(source=theme, theme_only=True)
        self.assertTrue(record['theme_checkout'])
        self.assertEqual((theme/'.git').read_text(), 'gitdir: /somewhere\n')
        self.assertFalse(any(entry['path'].endswith('/themes/dark-r') for entry in record['targets']))
    def test_other_directory_refuses_to_replace_a_theme_checkout(self):
        theme = self.place_checkout()
        other = Path(self.tmp.name)/'other'
        shutil.copytree(theme, other, ignore=shutil.ignore_patterns('.git'))
        (other/'.git').mkdir()
        with self.assertRaises(RuntimeError) as caught:
            m.install(self.home, source=other, apply=False, omarchy_path=self.platform)
        self.assertIn('git checkout', str(caught.exception))
        self.assertTrue((theme/'.git').is_dir())
        self.assertEqual((theme/'README.md').read_text(), 'keep\n')
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
        self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.workspaces').exists())
    def test_theme_checkout_reinstall_skips_theme_files(self):
        theme = self.place_checkout()
        self.install(source=theme)
        (theme/'colors.toml').write_text('local palette\n')
        qml = theme/'plugins/dark-r.stars/Stars.qml'
        qml.write_text(qml.read_text() + '\n// trail\n')
        record = self.install(source=theme, reinstall=True)
        self.assertTrue(record['theme_checkout'])
        self.assertEqual((theme/'colors.toml').read_text(), 'local palette\n')
        self.assertTrue((theme/'.git').is_dir())
        installed = self.home/'.config/omarchy/plugins/dark-r.stars/Stars.qml'
        self.assertIn('// trail', installed.read_text())
    def test_reinstall_drops_a_theme_directory_target(self):
        source = self.source_copy()
        self.install(source=source)
        marker = source/'keep.txt'
        marker.write_text('keep\n')
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        record['targets'].append({'path': str(source), 'saved': None, 'digest': 'old'})
        record_path.write_text(json.dumps(record))
        record = self.install(source=source, reinstall=True)
        self.assertEqual(marker.read_text(), 'keep\n')
        self.assertTrue((source/'.git').is_dir())
        self.assertFalse(any(entry['path'] == str(source) for entry in record['targets']))
        self.assertTrue((self.home/'.config/omarchy/plugins/dark-r.workspaces').is_dir())
    def test_theme_checkout_uninstall_leaves_the_theme(self):
        theme = self.place_checkout()
        self.current.write_text('dark-r\n')
        self.install(source=theme)
        seen = []
        def run(cmd, **kwargs):
            seen.append(list(cmd))
            if list(cmd)[:2] == ['hyprctl', 'configerrors']:
                return subprocess.CompletedProcess(cmd, 0, stdout='ok', stderr='')
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        with patch.object(m.subprocess, 'run', side_effect=run), patch.object(m, 'check_hyprland'):
            record = self.uninstall(source=theme, apply=True)
        self.assertTrue(record['theme_checkout'])
        self.assertFalse(any(cmd[:3] == ['omarchy', 'theme', 'set'] for cmd in seen))
        self.assertTrue((theme/'.git').is_dir())
        self.assertTrue((theme/'colors.toml').is_file())
        self.assertTrue((theme/'plugins/dark-r.workspaces').is_dir())
        self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.workspaces').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh').exists())
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
    def test_symlink_target_rejected(self):
        target = Path(self.tmp.name)/'important';target.mkdir()
        p = self.home/'.config/omarchy/themes/dark-r';p.parent.mkdir(parents=True)
        p.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeError): self.install()
        self.assertTrue(p.is_symlink())
    def test_symlinked_shell_json_is_written_through(self):
        versioned = Path(self.tmp.name)/'dotfiles'/'config'/'omarchy'/'shell.json'
        versioned.parent.mkdir(parents=True)
        versioned.write_bytes(self.shell.read_bytes())
        self.shell.unlink()
        self.shell.symlink_to(versioned)
        link = self.shell.readlink()
        self.install()
        self.assertEqual(self.shell.readlink(), link)
        self.assertEqual(json.loads(versioned.read_text())['bar']['layout']['center'][0]['id'], 'dark-r.workspaces')
        self.assertEqual(json.loads(versioned.read_text())['bar']['layout']['left'][1]['id'], 'dark-r.clock')
        self.assertFalse((versioned.parent/'shell.json.dark-r-tmp').exists())
        self.uninstall()
        self.assertEqual(self.shell.readlink(), link)
        self.assertEqual(json.loads(versioned.read_text()), BASE)

    # --- 2.0: components, retired files, record upgrade -------------------
    def downgrade_to_v1(self, theme_only=False):
        """Rewrite the record and files the way a 1.x install left them."""
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        record['version'] = 1
        record['theme_only'] = theme_only
        del record['components']
        del record['source_digest']
        record['corners_created_looknfeel'] = record.pop('geometry_created_looknfeel')
        hooks = self.home/'.config/omarchy/hooks'
        for helper, wrapper in (('dark-r-vscode-surfaces.py', 'theme-set.d/dark-r-vscode-surfaces.sh'),):
            for name in (helper, wrapper):
                (hooks/name).write_text('# 1.x\n')
                record['targets'].append({'path': str(hooks/name), 'saved': None, 'digest': m.digest(hooks/name)})
        if not theme_only:
            shell = json.loads(self.shell.read_text())
            shell['bar']['layout']['right'].insert(0, {'id': 'dark-r.weather', 'units': 'metric'})
            m.write_json(self.shell, shell)
            plugin = self.home/'.config/omarchy/plugins/dark-r.weather'
            plugin.mkdir(parents=True)
            (plugin/'BarWidget.qml').write_text('// 1.x copy\n')
            record['targets'].append({'path': str(plugin), 'saved': None, 'digest': m.digest(plugin)})
            record['replaced']['dark-r.weather'] = {'id': 'omarchy.weather'}
            cluster = record['bar_place'].get('cluster') or {}
            cluster.setdefault('centerEnd', []).append('dark-r.weather')
            record['bar_place']['cluster'] = cluster
        record_path.write_text(json.dumps(record))
        return record_path
    def test_reinstall_upgrades_a_v1_record_and_retires_old_files(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.downgrade_to_v1()
        self.install(source=source, reinstall=True)
        record = json.loads(record_path.read_text())
        self.assertEqual(record['version'], 2)
        self.assertEqual(record['components'], list(m.COMPONENTS))
        self.assertIn('geometry_created_looknfeel', record)
        self.assertNotIn('corners_created_looknfeel', record)
        self.assertFalse(any('vscode' in entry['path'] or 'dark-r.weather' in entry['path'] for entry in record['targets']))
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py').exists())
        self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.weather').exists())
        # The stock widget is back where the copy stood, with its settings.
        shell = json.loads(self.shell.read_text())
        self.assertEqual(shell['bar']['layout']['right'][0], {'id': 'omarchy.weather', 'units': 'metric'})
        self.assertIn('omarchy.weather', record['bar_place']['cluster']['centerEnd'])
        self.assertNotIn('dark-r.weather', record['bar_place']['cluster']['centerEnd'])
        self.uninstall(source=source)
        shell = json.loads(self.shell.read_text())
        self.assertIn({'id': 'omarchy.weather', 'units': 'metric'}, shell['bar']['layout']['right'])
    def test_reinstall_refuses_an_edited_retired_plugin(self):
        source = self.source_copy()
        self.install(source=source)
        self.downgrade_to_v1()
        widget = self.home/'.config/omarchy/plugins/dark-r.weather/BarWidget.qml'
        widget.write_text('// mine\n')
        shell = self.shell.read_bytes()
        with self.assertRaises(RuntimeError):
            self.install(source=source, reinstall=True)
        self.assertEqual(widget.read_text(), '// mine\n')
        self.assertEqual(self.shell.read_bytes(), shell)
    def test_uninstall_reads_a_v1_record(self):
        source = self.source_copy()
        self.install(source=source)
        self.downgrade_to_v1()
        self.uninstall(source=source)
        shell = json.loads(self.shell.read_text())
        ids = [entry['id'] for entries in shell['bar']['layout'].values() for entry in entries]
        self.assertFalse([i for i in ids if i.startswith('dark-r.')])
        self.assertIn('omarchy.weather', ids)
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py').exists())
        self.assertFalse((self.home/'.config/omarchy/plugins/dark-r.weather').exists())
    def test_light_v1_record_keeps_the_bar_out(self):
        source = self.source_copy()
        self.install(source=source, theme_only=True)
        record_path = self.downgrade_to_v1(theme_only=True)
        self.install(source=source, reinstall=True)
        self.assertEqual(json.loads(record_path.read_text())['components'], list(m.LIGHT_COMPONENTS))
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
    def test_components_install_only_what_was_asked(self):
        record = self.install(components=['bar'])
        hooks = self.home/'.config/omarchy/hooks'
        self.assertEqual(record['components'], ['bar'])
        self.assertTrue((self.home/'.config/omarchy/plugins/dark-r.workspaces').is_dir())
        self.assertFalse((hooks/'dark-r-gtk3.py').exists())
        self.assertFalse((hooks/'dark-r-firefox-chrome.py').exists())
        self.assertFalse((hooks/'dark-r-wallpapers.py').exists())
        self.assert_always_hooks()
        self.uninstall()
        self.assertFalse((hooks/'dark-r-geometry.py').exists())
    def test_firefox_is_its_own_component(self):
        self.install(components=['gtk'])
        hooks = self.home/'.config/omarchy/hooks'
        self.assertTrue((hooks/'dark-r-gtk3.py').is_file())
        self.assertFalse((hooks/'dark-r-firefox-chrome.py').exists())
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_unknown_component_is_refused(self):
        with self.assertRaises(ValueError):
            self.install(components=['bar', 'kde'])
        self.assertFalse((self.home/'.local/state/omarchy-dark-r').exists())
    def test_cli_rejects_components_with_reinstall(self):
        with patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                m.main(['--reinstall', 'gtk'])
            with self.assertRaises(SystemExit):
                m.main(['--light', 'bar'])
    def snapshot_tree(self):
        files = {}
        for path in sorted(self.home.rglob('*')):
            if path.is_file() and not path.is_symlink():
                files[str(path.relative_to(self.home))] = path.read_bytes()
        return files
    def test_dry_run_changes_nothing(self):
        source = self.source_copy()
        before = self.snapshot_tree()
        lines = self.install(source=source, dry_run=True)['dry_run']
        self.assertEqual(self.snapshot_tree(), before)
        self.assertTrue(any('dark-r.workspaces' in line and line.startswith('create') for line in lines))
        self.assertTrue(any('shell.json' in line for line in lines))
        self.assertTrue(any('looknfeel.lua' in line for line in lines))
        self.install(source=source)
        before = self.snapshot_tree()
        lines = self.install(source=source, reinstall=True, dry_run=True)['dry_run']
        self.assertEqual(self.snapshot_tree(), before)
        self.assertTrue(any(line.startswith('replace') for line in lines))
        lines = self.uninstall(source=source, dry_run=True)['dry_run']
        self.assertEqual(self.snapshot_tree(), before)
        self.assertTrue(any(line.startswith('remove') for line in lines))
    def test_install_records_the_checkout_state(self):
        source = self.source_copy()
        record = self.install(source=source)
        self.assertEqual(record['source_digest'], common.source_digest(source))
        (source/'plugins/dark-r.stars/Stars.qml').write_text('// next\n')
        record = self.install(source=source, reinstall=True)
        self.assertEqual(record['source_digest'], common.source_digest(source))

class GeometryHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.hook = load_script('geometry')
        self.look = self.home/'.config/hypr/looknfeel.lua'
        self.look.parent.mkdir(parents=True)
        self.user = 'hl.config({ input = { kb_layout = "us" } })\n'
        self.look.write_text(self.user)
        self.theme = self.home/'.local/state/omarchy/current/theme.name'
        self.theme.parent.mkdir(parents=True)
    def set_theme(self, name):
        self.theme.write_text(name + '\n')
        self.hook.apply(self.home, notify=False)
        return self.look.read_text() if self.look.exists() else None
    def test_block_follows_the_active_theme(self):
        text = self.set_theme('dark-r')
        self.assertIn('BEGIN Dark-R geometry', text)
        self.assertTrue(text.startswith(self.user))
        self.assertEqual(self.set_theme('dark-r'), text)
        self.assertEqual(self.set_theme('tokyo-night'), self.user)
        self.assertEqual(self.set_theme('dark-r'), text)
        self.hook.apply(self.home, clear=True)
        self.assertEqual(self.look.read_text(), self.user)
    def test_older_rounding_block_is_replaced(self):
        legacy = '-- BEGIN Dark-R corners\nhl.config({\n  decoration = {\n    rounding = 10,\n  },\n})\n-- END Dark-R corners\n'
        self.look.write_text(self.user + '\n' + legacy)
        text = self.set_theme('dark-r')
        self.assertNotIn('Dark-R corners', text)
        self.assertEqual(text.count('BEGIN Dark-R geometry'), 1)
        self.assertEqual(self.set_theme('nord'), self.user)
    def test_other_theme_without_the_file_creates_nothing(self):
        self.look.unlink()
        self.set_theme('nord')
        self.assertFalse(self.look.exists())
    def test_outdated_install_is_reported_once(self):
        checkout = self.home/'.config/omarchy/themes/dark-r'
        (checkout/'plugins/dark-r.stars').mkdir(parents=True)
        (checkout/'scripts').mkdir()
        (checkout/'plugins/dark-r.stars/Stars.qml').write_text('// installed\n')
        state = self.home/'.local/state/omarchy-dark-r'
        state.mkdir(parents=True)
        (state/'install.json').write_text(json.dumps({'source_digest': common.source_digest(checkout)}))
        self.theme.write_text('dark-r\n')
        with patch.object(self.hook.subprocess, 'run') as run:
            self.hook.apply(self.home)
            run.assert_not_called()
            (checkout/'plugins/dark-r.stars/Stars.qml').write_text('// pulled\n')
            self.hook.apply(self.home)
            self.hook.apply(self.home)
        self.assertEqual(run.call_count, 1)
        self.assertIn('--reinstall', ' '.join(run.call_args.args[0]))

class ThemeFiles(unittest.TestCase):
    """The files omarchy theme install delivers, with no installer."""
    # shell.toml keys Omarchy 4.5 reads. Checked against the installed Omarchy
    # below, so the list cannot quietly go stale.
    READ = {
        'bar': {'background', 'background-alpha', 'text', 'active', 'scale-with-font',
                'size-horizontal', 'size-vertical'},
        'controls': {'normal-color', 'normal-fill-alpha', 'normal-border-alpha', 'normal-border-width',
                     'hover-cursor-color', 'hover-cursor-fill-alpha', 'hover-cursor-border-alpha',
                     'hover-cursor-border-width', 'focus-color', 'focus-fill-alpha', 'focus-border-alpha',
                     'focus-border-width', 'selected-color', 'selected-fill-alpha', 'selected-border-alpha',
                     'selected-border-width', 'pressed-color', 'pressed-fill-alpha'},
        'popups': {'background', 'background-alpha', 'text', 'border', 'border-alpha', 'border-width'},
        'tooltip': {'background', 'background-alpha', 'text', 'border', 'border-alpha', 'border-width'},
        'notifications': {'background', 'background-alpha', 'text', 'border', 'border-alpha', 'border-width', 'countdown'},
        'menu': {'background', 'background-alpha', 'text', 'border', 'border-alpha', 'border-width', 'scrim',
                 'scrim-alpha', 'selected-background', 'selected-background-alpha', 'selected-text',
                 'selected-border', 'selected-border-alpha'},
        'polkit': {'background', 'background-alpha', 'text', 'text-error', 'border', 'border-error',
                   'border-alpha', 'scrim', 'scrim-alpha', 'accent'},
        'lock': {'background', 'background-alpha', 'text', 'placeholder', 'text-error', 'border',
                 'border-active', 'border-error', 'border-alpha', 'selection', 'selection-alpha'},
    }
    def shell(self):
        import tomllib
        return tomllib.loads((ROOT/'shell.toml').read_text())
    def test_shell_toml_sets_only_keys_omarchy_reads(self):
        for section, values in self.shell().items():
            if section == 'dark-r':
                continue
            self.assertIn(section, self.READ, section)
            self.assertLessEqual(set(values), self.READ[section], section)
    def test_read_list_matches_the_installed_omarchy(self):
        commons = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))/'shell/Commons'
        if not (commons/'Color.qml').is_file():
            self.skipTest('Omarchy is not installed')
        color = (commons/'Color.qml').read_text()
        style = (commons/'Style.qml').read_text()
        border = (commons/'Border.qml').read_text()
        for section, keys in self.READ.items():
            for key in keys:
                if section == 'controls' or key in ('scale-with-font', 'size-horizontal', 'size-vertical'):
                    found = f'"{key}"' in style
                elif key == 'border-width':
                    found = '"border-width"' in border
                else:
                    found = f'"{section}.{key}"' in color
                self.assertTrue(found, f'{section}.{key}')
    def test_dark_r_keys_are_the_ones_the_widgets_read(self):
        import re
        used = set()
        for qml in (ROOT/'plugins').rglob('*.qml'):
            text = qml.read_text()
            used |= set(re.findall(r'(?:pick\(|themeShellValues\[)"dark-r\.([a-z-]+)"', text))
            used |= set(re.findall(r'tone\("([a-z-]+)"', text))
        self.assertEqual(set(self.shell()['dark-r']), used)
    def test_resting_control_border_clears_three_to_one(self):
        import tomllib
        colors = tomllib.loads((ROOT/'colors.toml').read_text())
        controls = self.shell()['controls']
        border = common.blend(controls['normal-color'], colors['background'], controls['normal-border-alpha'])
        self.assertGreaterEqual(common.contrast(border, colors['background']), 3)
    def test_built_files_are_up_to_date(self):
        build = load_script('build')
        for name, text in build.outputs(ROOT).items():
            if text is None:
                continue  # Omarchy's renderer is not installed.
            self.assertEqual((ROOT/name).read_text(), text, name + ' is stale: run python3 scripts/build.py')
    def test_preview_compression_keeps_theme_colors_or_stays_lossless(self):
        try:
            import numpy  # noqa: F401
            from PIL import Image
        except ImportError:
            self.skipTest('numpy and Pillow are needed')
        build = load_script('build')
        theme = ['#ec8790', '#77af8a', '#0c040f']
        # A few flat theme swatches and a near-theme shade: 256 colors fit.
        flat = Image.new('RGB', (64, 64), '#0c040f')
        flat.paste(Image.new('RGB', (16, 16), '#ec8790'), (0, 0))
        flat.paste(Image.new('RGB', (16, 16), '#77af8a'), (16, 0))
        flat.paste(Image.new('RGB', (16, 16), '#eb8691'), (32, 0))
        result = build.quantize_keeping_palette(flat, theme)
        self.assertIsNotNone(result)
        self.assertEqual(result.convert('RGB').getpixel((4, 4)), (0xec, 0x87, 0x90))
        self.assertEqual(result.convert('RGB').getpixel((20, 4)), (0x77, 0xaf, 0x8a))
        # A full spectrum does not fit in 256 colors without visible change.
        import colorsys
        rainbow = Image.new('RGB', (256, 256))
        rainbow.putdata([tuple(int(c * 255) for c in colorsys.hsv_to_rgb(x / 256, y / 256, 1))
                         for y in range(256) for x in range(256)])
        self.assertIsNone(build.quantize_keeping_palette(rainbow, theme))
    def test_template_tokens_name_palette_keys(self):
        build = load_script('build')
        with self.assertRaises(ValueError):
            build.render('x = "{{ chartreuse }}"', build.palette(ROOT/'colors.toml'))
    def test_vscode_theme_carries_the_dark_r_chrome(self):
        import json as _json
        theme = _json.loads((ROOT/'vscode-theme.json').read_text())
        v = load_script('vscode_surfaces')
        for key, value in v.chrome(common.load_colors(ROOT/'colors.toml')).items():
            self.assertEqual(theme['colors'][key], value, key)
        self.assertTrue(theme['tokenColors'])

class Widgets(unittest.TestCase):
    """The QML of the Dark-R bar widgets, against the installed Omarchy."""
    def widgets(self):
        return sorted((ROOT/'plugins').rglob('*.qml'))
    def test_qml_parses(self):
        import re
        qmlformat = shutil.which('qmlformat')
        if not qmlformat:
            self.skipTest('qmlformat is not installed')
        with tempfile.TemporaryDirectory() as scratch:
            for qml in self.widgets():
                # qmlformat 1.0 stops at a typed function signature, which
                # Quickshell accepts, so drop the return type first.
                text = re.sub(r'\)\s*:\s*[A-Za-z_]+\s*\{', ') {', qml.read_text())
                check = Path(scratch)/qml.name
                check.write_text(text)
                result = subprocess.run([qmlformat, str(check)], capture_output=True)
                self.assertEqual(result.returncode, 0, str(qml.relative_to(ROOT)))
    def test_omarchy_members_exist(self):
        import re
        commons = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))/'shell/Commons'
        if not (commons/'Color.qml').is_file():
            self.skipTest('Omarchy is not installed')
        declared = {}
        for name in ('Color', 'Style', 'Util', 'I18n'):
            source = (commons/f'{name}.qml').read_text()
            declared[name] = set(re.findall(r'(?:property\s+[\w<>.]+\s+|function\s+)(\w+)', source))
        for qml in self.widgets():
            text = qml.read_text()
            for owner, member in re.findall(r'(?<![\w.])(Color|Style|Util|I18n)\.(\w+)', text):
                self.assertIn(member, declared[owner], f'{qml.relative_to(ROOT)}: {owner}.{member}')
    def test_no_hard_coded_install_path(self):
        for qml in self.widgets():
            self.assertFalse('/usr/share/omarchy' in qml.read_text(), str(qml.relative_to(ROOT)))
    def test_no_hex_colors_or_palette_sniffing(self):
        import re
        for qml in self.widgets():
            text = qml.read_text()
            self.assertFalse(re.findall(r'"#[0-9a-fA-F]{6,8}"', text), str(qml.relative_to(ROOT)))
    def test_motion_follows_the_animations_toggle(self):
        import re
        for qml in self.widgets():
            for value in re.findall(r'duration:\s*([^;}\n]+)', qml.read_text()):
                self.assertIn('Style.duration(', value, str(qml.relative_to(ROOT)))
    def test_ipc_goes_through_shellipc(self):
        for qml in self.widgets():
            self.assertFalse('IpcHandler' in qml.read_text(), str(qml.relative_to(ROOT)))
    def test_manifests_record_their_omarchy_base(self):
        for manifest in sorted((ROOT/'plugins').glob('*/manifest.json')):
            data = json.loads(manifest.read_text())
            self.assertEqual(data['id'], manifest.parent.name)
            self.assertNotEqual(data['author'], 'Omarchy', manifest.parent.name)
            if manifest.parent.name in ('dark-r.clock', 'dark-r.indicators', 'dark-r.menu', 'dark-r.workspaces'):
                self.assertRegex(data['omarchy'].get('basedOn', ''), r'^\d+\.\d+\.\d+$', manifest.parent.name)
        # The menu copy is only a bar widget. Claiming omarchy.menu would route
        # the Omarchy menu itself to it.
        menu = json.loads((ROOT/'plugins/dark-r.menu/manifest.json').read_text())
        self.assertNotIn('clonedFrom', menu.get('omarchy', {}))

def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PaletteHooks(unittest.TestCase):
    """GTK3, GTK4 and Firefox paint the same Dark-R roles."""
    def setUp(self):
        self.gtk3 = load_script('gtk3')
        self.gtk = load_script('gtk4-libadwaita')
        self.firefox = load_script('firefox-chrome')
        self.colors = self.gtk.load_colors(ROOT/'colors.toml')
    def test_hooks_share_one_role_table(self):
        # Every hook reads its roles from dark_r_common; none keeps a copy.
        import ast
        for name in ('gtk3', 'gtk4-libadwaita', 'firefox-chrome', 'vscode_surfaces', 'wallpapers'):
            tree = ast.parse((ROOT/'scripts'/f'{name}.py').read_text())
            defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
            self.assertFalse(defined & {'roles', 'load_colors', 'contrast', 'luminance', 'on_color', 'active_theme_name'}, name)
        self.assertIs(self.gtk.roles, common.roles)
        self.assertIs(self.firefox.roles, common.roles)
    def outputs(self):
        vscode = load_script('vscode_surfaces')
        return {
            'gtk3': self.gtk3.build_css(self.colors),
            'gimp': self.gtk3.build_gimp_css(self.colors),
            'gtk4': self.gtk.build_css(self.colors),
            'firefox chrome': self.firefox.build_chrome(self.colors),
            'firefox content': self.firefox.build_content(self.colors),
            'vscode': json.dumps(vscode.chrome(common.load_colors(ROOT/'colors.toml'))),
        }
    def test_hooks_use_palette_colors_only(self):
        import re, tomllib
        palette = {v.lower() for v in tomllib.loads((ROOT/'colors.toml').read_text()).values()
                   if isinstance(v, str) and v.startswith('#')}
        for name, text in self.outputs().items():
            # A two-digit alpha suffix on a palette color is still the palette.
            for color in re.findall(r'#[0-9a-fA-F]{6}(?![0-9a-fA-F]{1}\b)', text):
                self.assertIn(color.lower(), palette, name)
            self.assertNotRegex(text, r'\b(alpha|rgba?|mix|shade|oklab)\(', name)
    def test_css_hooks_set_colors_not_shapes(self):
        import re
        for name in ('gtk3', 'gimp', 'gtk4', 'firefox chrome', 'firefox content'):
            text = self.outputs()[name]
            self.assertNotRegex(text, r'\b(border-width|border-style|border-radius|padding|margin|min-width|min-height|font|text-shadow|-gtk-icon-shadow)\s*:', name)
            self.assertNotRegex(text, r'\bbackground\s*:', name)
            # Box shadows only where Adwaita draws a line with one.
            for shadow in re.findall(r'box-shadow:\s*([^;]*);', text):
                self.assertRegex(shadow, r'^inset (0 0 0 1px|0 -?4px|-?4px 0) #', name)
    def test_gtk3_keeps_adwaita_shapes(self):
        css = self.gtk3.build_css(self.colors)
        r = self.gtk.roles(self.colors)
        self.assertIn(f'notebook > header.top > tabs > tab:checked {{ box-shadow: inset 0 -4px {r["primary"]}; }}', css)
        self.assertIn(f'infobar.error > revealer > box {{ border-bottom-color: {r["error"]}; }}', css)
        self.assertIn(':not(:link):not(:visited),', css)
        self.assertIn(f'button.destructive-action:hover:not(:disabled) {{\n  background-color: {r["error_hover"]};', css)
        self.assertNotIn('button:active', css)
    def test_header_and_menus_match(self):
        gtk = self.gtk.build_css(self.colors)
        firefox = self.firefox.build_chrome(self.colors)
        r = self.gtk.roles(self.colors)
        self.assertIn(f'--headerbar-bg-color: {r["bar"]};', gtk)
        self.assertIn(f'--toolbar-background-color: {r["bar"]} !important;', firefox)
        self.assertIn(f'--popover-bg-color: {r["card"]};', gtk)
        self.assertIn(f'--panel-background-color: {r["card"]} !important;', firefox)
        self.assertIn(f'--accent-bg-color: {r["primary"]};', gtk)
        self.assertIn(f'--color-accent-primary: {r["primary"]} !important;', firefox)
    def test_roles(self):
        r = self.gtk.roles(self.colors)
        self.assertEqual(r['bar'], '#3f2c53')
        # Cyan is the space in view: active window, focused field.
        self.assertEqual(r['active'], '#96c5cf')
        self.assertEqual(r['hover'], '#f0a202')
        self.assertEqual(r['primary'], '#77af8a')
        self.assertEqual(r['focus'], '#fff3e6')
        self.assertEqual(r['warn'], '#f0a202')
        self.assertEqual(r['link'], '#d2bced')
    def test_active_and_menu_roles(self):
        import tomllib
        shell = tomllib.loads((ROOT/'shell.toml').read_text())
        colors = tomllib.loads((ROOT/'colors.toml').read_text())
        self.assertEqual(colors['hyprland_active_border'], colors['cyan'])
        self.assertEqual(shell['lock']['border-active'], colors['cyan'])
        # The Omarchy menu and launcher highlight is sage.
        self.assertEqual(shell['menu']['selected-background'], colors['green'])
        self.assertNotIn('launcher', shell)
        bar = shell['dark-r']
        # Current crumb is sage, outlined in the active-window cyan. Inactive
        # hover is bright green. Occupied is the dim foreground, empty is the
        # inactive border.
        self.assertEqual(bar['crumb-current'], colors['green'])
        self.assertEqual(bar['crumb-current-border'], colors['hyprland_active_border'])
        self.assertEqual(bar['crumb-hover'], colors['bright_green'])
        self.assertEqual(bar['crumb-occupied'], colors['dark_foreground'])
        self.assertEqual(bar['crumb-empty'], colors['hyprland_inactive_border'])
        self.assertEqual((bar['pill'], bar['pill-hover']), (colors['green'], colors['bright_green']))
        self.assertEqual(shell['notifications']['border'], colors['accent'])
    def test_text_on_fills_reads(self):
        r = self.gtk.roles(self.colors)
        for fill in ('primary', 'hover', 'error', 'warn', 'ok'):
            text = self.gtk.on_color(r[fill], r['bg'], r['fg'])
            self.assertGreaterEqual(common.contrast(r[fill], text), 4.5, fill)
    def test_no_translucent_washes(self):
        # Translucent amber over the dark surfaces reads as brown.
        for css in (self.gtk3.build_css(self.colors), self.gtk.build_css(self.colors), self.firefox.build_chrome(self.colors),
                    self.firefox.build_content(self.colors)):
            self.assertNotIn('color-mix', css)
    def test_firefox_button_text_stays_light(self):
        # --button-text-color is also panel menu text.
        self.assertNotIn('--button-text-color:', self.firefox.build_chrome(self.colors))
    def test_gtk4_window_controls_hover_round(self):
        css = self.gtk.build_css(self.colors)
        button = css.index('windowcontrols > button:hover:not(')
        self.assertGreater(button, css.index('/* Hover: solid amber'))
        self.assertIn('background-color: transparent;', css[button:button + 200])
        image = css.index('windowcontrols > button:hover > image {')
        self.assertIn('#f0a202', css[image:image + 120])
    def test_hover_is_solid_amber_with_dark_text(self):
        gtk = self.gtk.build_css(self.colors)
        chrome = self.firefox.build_chrome(self.colors)
        self.assertIn('--toolbarbutton-background-color-hover: #f0a202 !important;', chrome)
        self.assertIn('--button-text-color-hover: #0c040f !important;', chrome)
        self.assertIn('background-color: #f0a202;\n  color: #0c040f;', gtk)

    def test_gtk3_roles(self):
        css = self.gtk3.build_css(self.colors)
        self.assertIn('headerbar,\n.titlebar:not(headerbar) {\n  background-color: #3f2c53;', css)
        self.assertIn('button:link > label {\n  color: #d2bced;', css)
        self.assertIn('background-color: #f0a202;\n  background-image: none;\n  color: #0c040f;', css)
        self.assertIn('@define-color theme_selected_bg_color #77af8a;', css)
    def test_gtk3_apply_and_clear_keep_user_css(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.gtk3, 'restart_portal') as portal:
            home = Path(tmp)
            state = home/'.local/state/omarchy/current'
            (state/'theme').mkdir(parents=True)
            shutil.copy2(ROOT/'colors.toml', state/'theme/colors.toml')
            (state/'theme.name').write_text('dark-r\n')
            user = home/'.config/gtk-3.0/gtk.css'
            user.parent.mkdir(parents=True)
            user.write_text('/* mine */\n')
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertIn('omarchy-dark-r.css', user.read_text())
            self.assertIn('/* mine */', user.read_text())
            self.assertTrue((home/'.config/gtk-3.0/omarchy-dark-r.css').is_file())
            (state/'theme.name').write_text('nord\n')
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertEqual(user.read_text(), '/* mine */\n')
            self.assertFalse((home/'.config/gtk-3.0/omarchy-dark-r.css').exists())
            self.assertEqual(portal.call_count, 2)
    def test_gtk3_fill_text_stays_out_of_popups(self):
        # A GTK3 menu or popover is a CSS child of the item that opened it, and
        # that item stays hovered or checked: "menuitem:hover *" made every
        # label in an open menubar menu dark on dark.
        import re
        css = self.gtk3.build_css(self.colors)
        rules = re.sub(r'/\*.*?\*/|@define-color[^;]*;', '', re.sub(r'\s+', ' ', css))
        selectors = [sel.strip() for block in re.findall(r'([^{}]+)\{', rules) for sel in block.split(',')]
        reaching = [sel for sel in selectors if re.search(r'(\s|>\s*)\*$', sel) and not sel.startswith('tooltip')]
        self.assertTrue(reaching)
        for sel in reaching:
            self.assertIn('> :not(window):not(popover) *', sel)
        self.assertIn('menuitem:hover > :not(window):not(popover),', css)
    def test_gimp_colors_cover_the_default_theme(self):
        # Every color GIMP's Default theme defines, so no gray is left over.
        css = self.gtk3.build_gimp_css(self.colors)
        names = ('fg-color', 'bg-color', 'border-color', 'dimmed-fg-color', 'disabled-fg-color',
                 'disabled-button-color', 'hover-color', 'widget-bg-color', 'selected-color',
                 'extreme-bg-color', 'extreme-selected-color', 'strong-border-color',
                 'stronger-border-color', 'edge-border-color', 'scrollbar-slider-color',
                 'scrollbar-trough-color', 'ruler-color')
        for name in names:
            self.assertRegex(css, rf'@define-color {name} +#[0-9a-f]{{6}};')
        r = self.gtk3.roles(self.colors)
        self.assertRegex(css, rf'@define-color fg-color +{r["fg"]};')
        self.assertRegex(css, rf'@define-color bg-color +{r["card"]};')
    def test_gimp_apply_and_clear_keep_user_css(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.gtk3, 'restart_portal'):
            home = Path(tmp)
            state = home/'.local/state/omarchy/current'
            (state/'theme').mkdir(parents=True)
            shutil.copy2(ROOT/'colors.toml', state/'theme/colors.toml')
            (state/'theme.name').write_text('dark-r\n')
            mine = home/'.config/GIMP/3.0/gimp.css'
            mine.parent.mkdir(parents=True)
            mine.write_text('/* mine */\n')
            fresh = home/'.config/GIMP/3.2/gimp.css'
            fresh.parent.mkdir(parents=True)
            (home/'.config/GIMP/2.10').mkdir()
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertTrue(mine.read_text().startswith('/* mine */\n'))
            for path in (mine, fresh):
                self.assertEqual(path.read_text().count('BEGIN omarchy-dark-r gimp'), 1)
                self.assertIn('@define-color bg-color', path.read_text())
            self.assertFalse((home/'.config/GIMP/2.10/gimp.css').exists())
            (state/'theme.name').write_text('nord\n')
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertEqual(mine.read_text(), '/* mine */\n')
            self.assertFalse(fresh.exists())

class Wallpapers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'user'
        self.script = load_script('wallpapers')
        (self.home/'.local/state/omarchy/current').mkdir(parents=True)
        (self.home/'.local/state/omarchy/current/theme.name').write_text('dark-r\n')
        theme = self.home/'.config/omarchy/themes/dark-r/backgrounds'
        theme.mkdir(parents=True)
        (theme/'warp-cruise.png').write_bytes(b'bundled')
    def pictures(self, relative, contents, mtime):
        path = self.home/'Pictures/Wallpapers'/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        os.utime(path, (mtime, mtime))
        return path
    def test_top_level_pictures_are_linked_and_newest_is_chosen(self):
        self.pictures('2tier/older.jpg', b'older', 30)
        newer = self.pictures('newer.png', b'newer', 20)
        (self.home/'Pictures/Wallpapers/notes.txt').write_text('skip')
        self.pictures('black-1px.jpg', b'tiny', 5)
        kept = self.home/'.config/omarchy/backgrounds/dark-r/mine.png'
        kept.parent.mkdir(parents=True)
        kept.write_bytes(b'mine')
        stale = kept.parent/'2tier__older.jpg'
        stale.write_bytes(b'stale')
        record = self.home/'.local/state/omarchy-dark-r/wallpapers.json'
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({'files': {'2tier__older.jpg': str(self.home/'Pictures/Wallpapers/2tier/older.jpg')}}))
        chosen = self.script.sync(self.home)
        directory = self.home/'.config/omarchy/backgrounds/dark-r'
        self.assertFalse(stale.exists())
        self.assertFalse((directory/'older.jpg').exists())
        self.assertEqual((directory/'newer.png').stat().st_ino, newer.stat().st_ino)
        self.assertEqual(chosen, directory/'newer.png')
        self.assertEqual(kept.read_bytes(), b'mine')
        self.assertFalse((directory/'notes.txt').exists())
        self.assertTrue((directory/'black-1px.jpg').exists())
        link = self.home/'.local/state/omarchy/current/background'
        link.symlink_to(chosen)
        self.assertIsNone(self.script.sync(self.home))
    def test_other_theme_links_without_choosing(self):
        self.pictures('one.jpg', b'one', 10)
        (self.home/'.local/state/omarchy/current/theme.name').write_text('nord\n')
        self.assertIsNone(self.script.sync(self.home))
        self.assertTrue((self.home/'.config/omarchy/backgrounds/dark-r/one.jpg').is_file())
    def test_empty_folder_uses_nothing_and_clear_removes_links(self):
        self.pictures('one.jpg', b'one', 10)
        chosen = self.script.sync(self.home)
        link = self.home/'.local/state/omarchy/current/background'
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(chosen)
        folder = self.home/'Pictures/Wallpapers'
        for path in folder.rglob('*'):
            if path.is_file():
                path.unlink()
        self.assertEqual(self.script.sync(self.home), self.home/'.config/omarchy/themes/dark-r/backgrounds/warp-cruise.png')
        self.assertFalse((self.home/'.config/omarchy/backgrounds/dark-r/one.jpg').exists())
        self.pictures('back.jpg', b'back', 30)
        shown = self.script.sync(self.home)
        link.unlink()
        link.symlink_to(shown)
        self.assertEqual(self.script.clear(self.home), self.home/'.config/omarchy/themes/dark-r/backgrounds/warp-cruise.png')
        self.assertFalse(shown.exists())
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/wallpapers.json').exists())
    def test_missing_folder_leaves_the_bundled_wallpaper(self):
        self.assertIsNone(self.script.sync(self.home))
        self.assertFalse((self.home/'.config/omarchy/backgrounds/dark-r').exists())
    def test_extra_bundled_wallpapers_leave_warp_cruise_as_the_fallback(self):
        theme = self.home/'.config/omarchy/themes/dark-r/backgrounds'
        (theme/'3sync-4k.png').write_bytes(b'fluid')
        (theme/'omarchy.webp').write_bytes(b'wordmark')
        self.pictures('one.jpg', b'one', 10)
        chosen = self.script.sync(self.home)
        link = self.home/'.local/state/omarchy/current/background'
        link.symlink_to(chosen)
        for path in (self.home/'Pictures/Wallpapers').iterdir():
            if path.is_file():
                path.unlink()
        self.assertEqual(self.script.sync(self.home), theme/'warp-cruise.png')

if __name__ == '__main__': unittest.main()
