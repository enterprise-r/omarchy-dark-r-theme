import QtQuick
import qs.Commons
import qs.Ui

// Structural Dark-R endcap; no click target or simulated telemetry. It takes
// no space with any other theme.
BarWidget {
  id: root
  // The look follows the active theme's shell.toml, not the palette.
  readonly property bool darkR: Color.themeShellValues["dark-r.theme"] === "dark-r"
  implicitWidth: darkR ? Style.space(Number(setting("size", 38))) : 0
  implicitHeight: barSize
  Rectangle {
    visible: root.darkR
    anchors.centerIn: parent
    width: Math.max(0, parent.width - 6)
    height: parent.height - 8
    topLeftRadius: root.setting("end", "left") === "left" ? height / 2 : 1
    bottomLeftRadius: topLeftRadius
    topRightRadius: root.setting("end", "left") === "right" ? height / 2 : 1
    bottomRightRadius: topRightRadius
    // A "color" setting on the widget wins over the theme's dark-r.band.
    color: Color.flatColor(root.setting("color", Color.pick("dark-r.band", "")), Color.accent)
  }
}
