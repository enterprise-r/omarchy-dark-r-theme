import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Date/time label for the bar, and the host for the calendar popup.
//
// Left click reveals the calendar — asking "what is the date?" is what a
// click on a clock means — right click walks the common label formats, and
// middle click opens the timezone picker.
//
// Based on Omarchy 4.5.0 plugins/panels/clock/BarWidget.qml. Dark-R changes
// are marked "Dark-R". The calendar is Omarchy's own panel, loaded from the
// running shell, so it keeps every fix and translation. Model.js and
// WallClock.qml are Omarchy's, unchanged.
BarWidget {
  id: root
  moduleName: "omarchy.clock"

  // Dark-R: the look follows the active theme's shell.toml, not the palette.
  // On a horizontal bar the label is a fixed stardate chip, in capitals.
  readonly property bool darkR: Color.themeShellValues["dark-r.theme"] === "dark-r"
  readonly property bool chip: root.darkR && !root.vertical
  readonly property string chipFormat: "yyyyMM.dd ddd HH:mm"

  function tone(key, fallback) {
    return Color.flatColor(Color.pick("dark-r." + key, ""), fallback)
  }

  property date displayDate: clock.date

  readonly property string configuredFormat: vertical
    ? setting("verticalFormat", "HH\n—\nmm")
    : (root.chip ? root.chipFormat : setting("format", "dddd HH:mm"))
  readonly property string configuredAltFormat: vertical
    ? setting("verticalFormatAlt", "dd\nMMM\n'W'ww\n''yy")
    : setting("formatAlt", "d MMMM 'W'ww yyyy")

  readonly property var formatRing: Model.clockFormatRing(configuredFormat, configuredAltFormat, Model.clockFormats(vertical))

  // What the bar shows is what shell.json stores, so a cycled format is the
  // format from then on rather than something that reverts on restart.
  readonly property string activeFormat: configuredFormat

  // A seconds label needs the clock to tick sixty times as often, and a
  // repaint a second is a price only the formats that print seconds pay.
  readonly property bool showsSeconds: Model.clockNeedsSeconds(activeFormat)
  readonly property string displayText: formatted(displayDate)
  readonly property var verticalLines: displayText.split("\n")

  function refresh() {
    displayDate = new Date()
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function cycleFormat() {
    // Dark-R: the chip keeps its label. shell.json `format` is left alone, so
    // another theme gets the label chosen there.
    if (root.chip) return
    var current = String(configuredFormat)
    var next = Model.nextClockFormat(formatRing, current)
    if (next === "" || next === current) return

    var entry = { id: root.moduleName }
    for (var key in root.settings) if (key !== "id") entry[key] = root.settings[key]
    entry[vertical ? "verticalFormat" : "format"] = next

    // Applied locally first so the label changes on the click itself; the
    // shell.json write comes back through the bar as the same value.
    root.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  // Day and month names follow the Omarchy language, not the system locale,
  // which only catches up at the next login.
  readonly property var formatLocale: Qt.locale(I18n.formatLocale)

  // The ISO week goes in as a literal, so its digits are localized here the
  // way Qt localizes the rest of the format.
  function formatted(date) {
    var week = Model.isoWeekLiteral(date.getFullYear(), date.getMonth(), date.getDate())
    week = week.split("").map(function(digit) { return I18n.formatNumber(digit) }).join("")
    return date.toLocaleString(root.formatLocale, activeFormat.replace(/ww/g, week))
  }

  // ---- Calendar popup. Shape contract for shell.summon/hide/toggle
  //      routing: Bar.findPanelWidget requires open/close/opened on the
  //      bar-widget root.
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function togglePanel() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  function toggleWeekStart() {
    if (panelLoader.item) panelLoader.item.toggleWeekStart()
  }

  // The clock fills more slot than it paints a mark for, at both
  // orientations: horizontally it is a text label in a padded slot, so the
  // dot takes the label width; vertically it is a stack of icon-sized lines,
  // so the dot takes one line — the same mark every icon widget gets, rather
  // than a rule running the height of the whole stack.
  readonly property real openPanelIndicatorWidth: button.labelWidth
  readonly property real openPanelIndicatorHeight: Math.max(Style.space(10), Math.round(Style.bar.iconSlot * 0.55))

  // Forwarded so this widget can stand in for the panel as the bar's popout
  // identity: Bar.requestPopout prefers closeForPopoutSwitch over close, and
  // KeyboardPanel reads popoutSwitchClosing back off its owner.
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  WallClock {
    id: clock
    step: root.showsSeconds ? 1000 : 60000
    onDateChanged: root.displayDate = date
  }

  Loader {
    id: panelLoader
    active: true
    // Dark-R: Omarchy's calendar from the shell that is running. A relative
    // path would look beside this copy.
    source: "file://" + Quickshell.shellDir + "/plugins/panels/clock/Panel.qml"
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  ShellIpc {
    target: "omarchy.clock"

    function refresh(): void { root.broadcast("refresh") }
    function cycleFormat(): void { root.cycleFormat() }
    function toggleWeekStart(): void { root.toggleWeekStart() }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.togglePanel() }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical ? "" : (root.chip ? root.displayText.toUpperCase() : root.displayText)
    foreground: root.chip ? root.tone("ink", Color.background) : (root.bar ? root.bar.barForeground : Color.foreground)
    labelVisible: !root.vertical
    hasVisualContent: root.vertical ? root.verticalLines.length > 0 : text !== ""
    fixedHeight: root.vertical ? root.verticalLines.length * Style.bar.iconSlot : -1
    // Dark-R: clears the chip's rounded ends.
    horizontalMargin: root.chip ? 16 : 8.75
    verticalPadding: 8.75
    tooltipText: root.chip ? "" : I18n.t("clock.toggleFormat")
    // The clock is text to read, not an icon to press, so a click never
    // shrinks it; the format it cycles to, or the panel it opens, is feedback.
    pressFeedbackButtons: Qt.NoButton

    onPressed: function(b) {
      if (b === Qt.RightButton) root.cycleFormat()
      else if (b === Qt.MiddleButton) { if (root.bar) root.bar.run("omarchy-menu-timezone") }
      else root.togglePanel()
    }

    // Dark-R: the chip. Its height and radius match the Omarchy button pill.
    Rectangle {
      visible: root.chip
      z: -1
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      height: parent.height - 2
      radius: Style.cornerRadius
      color: root.tone("clock", Color.muted)
    }

    Column {
      visible: root.vertical
      anchors.fill: parent

      Repeater {
        model: root.verticalLines

        OpticalGlyph {
          required property string modelData
          width: button.width
          height: Style.bar.iconSlot
          text: modelData
          fontFamily: button.fontFamily
          fontSize: modelData.length > 3
            ? button.fontSize * 0.9
            : button.fontSize
          color: button.foreground
        }
      }
    }
  }
}
