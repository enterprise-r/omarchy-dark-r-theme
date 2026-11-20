import QtQuick
import qs.Commons
import qs.Ui

// The Omarchy button. With Dark-R it is a sage pill that meets the screen
// edge. With any other theme it is Omarchy's own button, unchanged.
// Based on Omarchy 4.5.0 plugins/menu/BarWidget.qml.
BarWidget {
  id: root
  moduleName: "omarchy.menu"
  // The Dark-R look follows the active theme's shell.toml, not the palette,
  // so a colors.toml overlay keeps it.
  readonly property bool darkR: Color.themeShellValues["dark-r.theme"] === "dark-r"
  // LeftModules insets the group by space(8). Cancel that so the pill meets
  // the screen edge. sideGap stays between this pill and the next control.
  readonly property int sideGap: Style.space(3)
  readonly property int edgeInset: Style.space(8)

  function tone(key, fallback) {
    return Color.flatColor(Color.pick("dark-r." + key, ""), fallback)
  }

  function open(button) {
    if (!root.bar) return
    if (button === Qt.RightButton) root.bar.run("xdg-terminal-exec")
    else root.bar.run("omarchy-shell shell toggle omarchy.menu '{\"menu\":\"root\"}'")
  }

  implicitWidth: content.item ? content.item.implicitWidth : 0
  implicitHeight: content.item ? content.item.implicitHeight : 0

  // One button exists at a time: each registers itself as a click target.
  Loader {
    id: content
    sourceComponent: root.darkR ? pillButton : stockButton
  }

  Component {
    id: stockButton

    Item {
      implicitWidth: button.implicitWidth
      implicitHeight: button.implicitHeight
      width: root.width
      height: root.height

      BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: ""
        fontFamily: "omarchy"
        onPressed: function(button) { root.open(button) }
      }
    }
  }

  Component {
    id: pillButton

    Item {
      implicitWidth: button.implicitWidth
      implicitHeight: button.implicitHeight
      width: root.width
      height: root.height

      WidgetButton {
        id: button
        anchors.fill: parent
        anchors.leftMargin: -root.edgeInset
        anchors.rightMargin: root.sideGap
        bar: root.bar
        text: ""
        fontFamily: "omarchy"
        fontSize: 18
        foreground: root.tone("ink", Color.background)
        fixedWidth: Style.space(32) - root.edgeInset + root.sideGap * 2
        horizontalMargin: 7.5
        // The stock label centers on the full button, below this shorter
        // pill, and the glyph leans right in its em box. Draw it here instead.
        labelVisible: false
        onPressed: function(button) { root.open(button) }

        Rectangle {
          id: pill
          z: -1
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          height: parent.height - 2
          // Same curve as the window corners. Style.cornerRadius tracks
          // Hyprland's decoration:rounding.
          radius: Style.cornerRadius
          // Resting sage. Hover matches an inactive workspace crumb.
          color: button.tooltipHovered ? root.tone("pill-hover", Color.accent) : root.tone("pill", Color.accent)
          Behavior on color { ColorAnimation { duration: Style.duration(120) } }
        }

        Text {
          anchors.centerIn: pill
          anchors.horizontalCenterOffset: -0.5
          textFormat: Text.PlainText
          text: ""
          color: button.foreground
          font.family: "omarchy"
          font.pixelSize: button.fontSize
          renderType: Text.NativeRendering
        }
      }
    }
  }
}
