# Generated from colors.toml by scripts/build.py. Edit templates/shell.toml.tpl.
#
# Dark-R shell roles, named as in colors.toml:
#   hover           accent              {{ accent }}
#   keyboard focus  bright_foreground   {{ bright_foreground }}
#   current/chosen  green               {{ green }}
#   active, in view cyan                {{ cyan }}   (active window, lock field)
#   cards, panels   lighter_background  {{ lighter_background }}, border dark_foreground {{ dark_foreground }}
#   dim text        dark_foreground     {{ dark_foreground }}   (placeholders)
#   notices         info blue, ok green, warn accent, error red;
#                   desktop notifications use accent
# Borders and focus rings clear 3:1 on the background.

[bar]
background = "{{ background }}"
background-alpha = 1.0
text = "{{ light_foreground }}"
# Modules asking for attention read as a warning notice.
active = "{{ accent }}"
scale-with-font = true
size-horizontal = 32
size-vertical = 32

[controls]
# Omarchy draws each control border in the color of its state.
normal-color = "{{ foreground }}"
normal-fill-alpha = 0.06
# The resting border is foreground at 0.6, close to dark_foreground.
normal-border-alpha = 0.6
normal-border-width = 1
hover-cursor-color = "{{ accent }}"
hover-cursor-fill-alpha = 0.15
hover-cursor-border-alpha = 1.0
focus-color = "{{ bright_foreground }}"
focus-border-alpha = 1.0
focus-fill-alpha = 0.16
selected-color = "{{ green }}"
selected-fill-alpha = 0.18
selected-border-width = 1
selected-border-alpha = 1.0

[popups]
background = "{{ lighter_background }}"
background-alpha = 1.0
text = "{{ foreground }}"
border = "{{ dark_foreground }}"
border-width = 1

[tooltip]
background = "{{ lighter_background }}"
background-alpha = 1.0
text = "{{ foreground }}"
border = "{{ dark_foreground }}"
# A 1px rounded border loses its outer bottom pixel, so that edge is thicker.
border-width = "1 1 2"

[notifications]
background = "{{ lighter_background }}"
background-alpha = 1.0
text = "{{ foreground }}"
# Notifications ask for attention: amber, as the bar's attention state.
border = "{{ accent }}"
border-width = "3 1 1"
countdown = "{{ accent }}"

[menu]
# The Omarchy menu and the app launcher share these colors. Their rows are
# places to go: the highlighted row is the chosen one, sage.
background = "{{ lighter_background }}"
background-alpha = 1.0
text = "{{ foreground }}"
border = "{{ dark_foreground }}"
border-width = "4 1 1"
scrim = "{{ background }}"
scrim-alpha = 0.55
selected-background = "{{ green }}"
selected-background-alpha = 1.0
selected-text = "{{ background }}"
selected-border = "{{ green }}"
selected-border-alpha = 1.0

[polkit]
background = "{{ lighter_background }}"
background-alpha = 1.0
text = "{{ foreground }}"
text-error = "{{ red }}"
border = "{{ dark_foreground }}"
border-error = "{{ red }}"
border-alpha = 1.0
scrim = "{{ background }}"
scrim-alpha = 0.55
accent = "{{ accent }}"

[lock]
background = "{{ lighter_background }}"
background-alpha = 1.0
text = "{{ foreground }}"
placeholder = "{{ dark_foreground }}"
text-error = "{{ red }}"
border = "{{ dark_foreground }}"
border-active = "{{ cyan }}"
border-error = "{{ red }}"
selection = "{{ hyprland_inactive_border }}"
selection-alpha = 1.0

[dark-r]
# Read by the Dark-R bar widgets that ./install.sh adds. The theme marker
# turns their Dark-R look on. With any other theme they draw like the stock
# widgets. A key in ~/.config/omarchy/shell.toml overrides the color here.
theme = "dark-r"
# Text on a filled pill or crumb.
ink = "{{ background }}"
# The Omarchy button.
pill = "{{ green }}"
pill-hover = "{{ bright_green }}"
# The clock chip.
clock = "{{ dark_foreground }}"
# Workspace crumbs. The current one is sage, outlined in the active-window cyan.
crumb-current = "{{ green }}"
crumb-current-border = "{{ cyan }}"
crumb-occupied = "{{ dark_foreground }}"
crumb-empty = "{{ hyprland_inactive_border }}"
crumb-empty-text = "{{ bright_foreground }}"
crumb-hover = "{{ bright_green }}"
# An active indicator icon.
indicator-active = "{{ green }}"
# The plate under dark bar text, when a bright wallpaper turns that text dark.
plate-light = "{{ foreground }}"
# The starfield.
star = "{{ bright_cyan }}"
star-head = "{{ foreground }}"
star-tail = "{{ blue }}"
star-tail-warm = "{{ brown }}"
# The band endcap.
band = "{{ orange }}"
