"""VS Code chrome in the Dark-R roles.

Omarchy's generated theme paints every region with one background and uses
translucent accent washes for hover and selection. These are the workbench
colors Dark-R sets instead, from the same roles as the GTK and Firefox hooks:
the code well stays `background`, sidebars, panels and fields are cards, the
title bar is the app header strip, the current tab is sage, keyboard rows in
the launcher, suggestions and menus are solid amber, and warnings are amber.

VS Code has no hover color for match highlights or toolbar icons, so lists
and toolbars hover with the quiet inactive-border fill instead of amber; an
amber fill would hide the amber matches and the light icons. The keyboard
cursor in those lists is a solid amber outline.

scripts/build.py applies them to Omarchy's own template and writes
vscode-theme.json into the theme. Omarchy uses a file a theme ships in place
of the one it would generate, so this needs no hook.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dark_r_common import luminance, on_color, roles  # noqa: E402


def chrome(colors: dict[str, str]) -> dict[str, str]:
    """Workbench colors for a dark theme; empty for a light one."""
    r = roles(colors)
    bg, fg, card, line, edge = r["bg"], r["fg"], r["card"], r["line"], r["edge"]
    if luminance(bg) > luminance(fg):
        return {}
    dim, bright, hover, primary = r["dim"], r["bright"], r["hover"], r["primary"]
    on_hover = on_color(hover, bg, fg)
    on_primary = on_color(primary, bg, fg)
    on_primary_hover = on_color(r["primary_hover"], bg, fg)
    on_warn = on_color(r["warn"], bg, fg)
    warn = r["warn"]
    sel = colors.get("selection", line)

    return {
        # Code well.
        "editor.background": bg,
        "editorGutter.background": bg,
        "editorPane.background": bg,
        "editorGroup.emptyBackground": bg,
        "breadcrumb.background": bg,
        "terminal.background": bg,
        "outputView.background": bg,
        "welcomePage.background": bg,
        "editor.lineHighlightBackground": card,
        "editor.lineHighlightBorder": line,

        # Selection is opaque: the generated
        # theme's translucent wash barely shows on the dark well. Guides and
        # rulers use the line, so structure shows without competing with code.
        "editor.selectionBackground": sel,
        "editor.inactiveSelectionBackground": line,
        "terminal.selectionBackground": sel,
        "terminal.inactiveSelectionBackground": line,
        "editorIndentGuide.background1": line,
        "editorIndentGuide.activeBackground1": dim,
        "editorWhitespace.foreground": line,
        "editorRuler.foreground": line,

        # App header strip, as the GTK header bar and Firefox toolbar.
        "titleBar.activeBackground": r["bar"],
        "titleBar.activeForeground": fg,
        "titleBar.inactiveBackground": card,
        "titleBar.inactiveForeground": fg,
        "titleBar.border": edge,

        # Cards: sidebars, panels, frame. Quiet rules keep regions apart.
        "panel.background": card,
        "panel.border": line,
        "sideBar.background": card,
        "sideBar.border": line,
        "sideBarTitle.foreground": fg,
        "sideBarSectionHeader.background": card,
        "sideBarSectionHeader.border": line,
        "panelSectionHeader.background": card,
        "activityBar.background": card,
        "activityBar.border": line,
        "statusBar.background": card,
        "statusBar.border": line,
        "statusBar.noFolderBackground": card,
        "statusBar.noFolderBorder": line,
        "editorGroupHeader.tabsBackground": card,
        "editorGroupHeader.noTabsBackground": card,
        "editorGroupHeader.tabsBorder": line,
        "editorGroupHeader.border": line,
        "editorGroup.border": line,
        "terminal.border": line,
        "welcomePage.tileBackground": card,
        "peekViewEditor.background": card,
        "peekViewEditorGutter.background": card,
        "peekViewResult.background": card,
        "peekViewTitle.background": card,
        "commandCenter.background": card,
        "notificationCenterHeader.background": card,
        "quickInputTitle.background": card,
        "debugToolBar.background": card,
        "outputViewStickyScroll.background": card,

        # Popups are cards with a dim edge.
        "widget.border": edge,
        "editorWidget.background": card,
        "editorWidget.border": edge,
        "editorHoverWidget.background": card,
        "editorHoverWidget.border": edge,
        "editorSuggestWidget.background": card,
        "editorSuggestWidget.border": edge,
        "editorMarkerNavigation.background": card,
        "quickInput.background": card,
        "menu.background": card,
        "menu.border": edge,
        "notifications.background": card,
        "notifications.border": edge,
        "notificationToast.border": edge,
        "breadcrumbPicker.background": card,
        "listFilterWidget.background": card,

        # Fields: card fill, dim border, dim placeholder.
        "input.background": card,
        "input.border": edge,
        "input.placeholderForeground": dim,
        "dropdown.background": card,
        "dropdown.listBackground": card,
        "dropdown.border": edge,
        "checkbox.background": card,
        "checkbox.border": edge,
        "checkbox.selectBackground": card,
        "checkbox.selectBorder": edge,
        "settings.dropdownBackground": card,
        "settings.textInputBackground": card,
        "settings.numberInputBackground": card,
        "settings.checkboxBackground": card,
        "descriptionForeground": dim,
        "editorLineNumber.foreground": dim,

        # Tabs: sage marks the current one, amber is hover.
        "tab.activeBackground": bg,
        "tab.activeForeground": primary,
        "tab.activeBorder": primary,
        "tab.activeBorderTop": primary,
        "tab.unfocusedActiveBackground": card,
        "tab.unfocusedActiveBorderTop": primary,
        "tab.inactiveBackground": card,
        "tab.unfocusedInactiveBackground": card,
        "tab.inactiveForeground": dim,
        "tab.unfocusedInactiveForeground": dim,
        "tab.border": line,
        "tab.hoverBackground": hover,
        "tab.hoverForeground": on_hover,
        "tab.unfocusedHoverBackground": hover,
        "tab.unfocusedHoverForeground": on_hover,
        "tab.hoverBorder": hover,

        # Activity bar: sage for the current view, no wash behind it.
        "activityBar.foreground": primary,
        "activityBar.inactiveForeground": fg,
        "activityBar.activeBorder": primary,
        "activityBar.activeBackground": card,

        # Launcher, suggestions and menus: the keyboard row is solid amber.
        "quickInputList.focusBackground": hover,
        "quickInputList.focusForeground": on_hover,
        "quickInputList.focusIconForeground": on_hover,
        "list.focusHighlightForeground": on_hover,
        "editorSuggestWidget.selectedBackground": hover,
        "editorSuggestWidget.selectedForeground": on_hover,
        "editorSuggestWidget.selectedIconForeground": on_hover,
        "editorSuggestWidget.focusHighlightForeground": on_hover,
        "menu.selectionBackground": hover,
        "menu.selectionForeground": on_hover,
        "menu.selectionBorder": hover,
        "menubar.selectionBackground": hover,
        "menubar.selectionForeground": on_hover,
        "statusBarItem.hoverBackground": hover,
        "statusBarItem.hoverForeground": on_hover,
        "statusBarItem.prominentHoverBackground": hover,
        "statusBarItem.prominentHoverForeground": on_hover,
        "statusBarItem.remoteHoverBackground": hover,
        "statusBarItem.remoteHoverForeground": on_hover,

        # Trees and lists keep amber matches readable: quiet fills, the
        # keyboard cursor as an amber outline, the chosen row in sage.
        "list.hoverBackground": line,
        "list.hoverForeground": fg,
        "list.focusBackground": line,
        "list.focusForeground": fg,
        "list.focusOutline": hover,
        "list.focusAndSelectionOutline": hover,
        "list.activeSelectionBackground": line,
        "list.activeSelectionForeground": primary,
        "list.activeSelectionIconForeground": primary,
        "list.inactiveSelectionBackground": line,
        "list.inactiveSelectionForeground": fg,
        "list.inactiveFocusBackground": line,
        "list.inactiveFocusOutline": edge,
        "list.highlightForeground": hover,
        "toolbar.hoverBackground": line,
        "toolbar.activeBackground": line,
        "inputOption.hoverBackground": line,
        "settings.focusedRowBackground": line,
        "settings.focusedRowBorder": hover,
        "settings.rowHoverBackground": line,
        "peekViewResult.selectionBackground": line,

        # Buttons and toggles: sage when suggested or on, amber on hover.
        "button.background": primary,
        "button.foreground": on_primary,
        "button.hoverBackground": r["primary_hover"],
        "button.border": edge,
        "button.secondaryBackground": line,
        "button.secondaryForeground": fg,
        "button.secondaryHoverBackground": card,
        "inputOption.activeBackground": primary,
        "inputOption.activeForeground": on_primary,
        "inputOption.activeBorder": primary,
        "progressBar.background": primary,

        # Focus and links.
        "focusBorder": r["focus"],
        "textLink.foreground": r["link"],
        "textLink.activeForeground": r["link_hover"],

        # Notices: warnings are amber; info, error stay blue and red.
        "editorWarning.foreground": warn,
        "editorWarning.background": f"{warn}15",
        "editorOverviewRuler.warningForeground": warn,
        "minimap.warningHighlight": warn,
        "problemsWarningIcon.foreground": warn,
        "notificationsWarningIcon.foreground": warn,
        "list.warningForeground": warn,
        "inputValidation.warningForeground": warn,
        "inputValidation.warningBorder": warn,
        "inputValidation.warningBackground": f"{warn}20",
        "editorMarkerNavigationWarning.background": f"{warn}20",
        "editorMarkerNavigationWarning.headerBackground": f"{warn}15",
        "debugConsole.warningForeground": warn,
        "statusBarItem.warningBackground": warn,
        "statusBarItem.warningForeground": on_warn,
        "statusBarItem.warningHoverBackground": warn,
        "statusBarItem.warningHoverForeground": on_warn,
        "editorInfo.foreground": r["info"],
        "notificationsInfoIcon.foreground": r["info"],
        "editorError.foreground": r["error"],
        "notificationsErrorIcon.foreground": r["error"],
    }


def patch_theme(data: dict, colors: dict[str, str]) -> dict:
    """Omarchy's generated VS Code theme with the Dark-R workbench colors."""
    workbench = data.get("colors")
    if not isinstance(workbench, dict):
        raise ValueError("vscode-theme.json has no colors table")
    out = dict(data)
    out["colors"] = {**workbench, **chrome(colors)}
    return out
