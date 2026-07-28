#!/usr/bin/env python3
import json
import os
import signal
import socket
import subprocess
import threading
import urllib.error
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, GLib, Gtk, Pango


ROOT = os.path.dirname(os.path.abspath(__file__))
MIXED_PORT = int(os.environ.get("MIXED_PORT", "29674"))
CONTROLLER_PORT = int(os.environ.get("CONTROLLER_PORT", "29090"))
WEBUI_PORT = int(os.environ.get("WEBUI_PORT", "29100"))
CORE_API = f"http://127.0.0.1:{CONTROLLER_PORT}"
WEBUI_URL = f"http://127.0.0.1:{WEBUI_PORT}"
PROXY_URL = f"http://127.0.0.1:{MIXED_PORT}"
GROUP = "Tyty"


class TytyIndicator:
    def __init__(self):
        self.current_node = "-"
        self.running = False
        self.window = None
        self.status_value = None
        self.node_value = None
        self.refresh_active = False
        self.test_active = False

        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "tyty-wine-core",
            "network-vpn-symbolic",
            AyatanaAppIndicator3.IndicatorCategory.SYSTEM_SERVICES,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()
        self.status_item = self._disabled_item("状态：正在连接")
        self.node_item = self._disabled_item("当前节点：-")
        self.menu.append(self.status_item)
        self.menu.append(self.node_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        show_item = self._action_item("打开状态窗口", self.show_window)
        self.menu.append(show_item)
        self.menu.append(self._action_item("打开 WebUI", self.open_webui))
        self.test_item = self._action_item("测试连接", self.test_connection)
        self.menu.append(self.test_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.menu.append(self._action_item("停止代理", self.stop_proxy))
        self.menu.show_all()

        self.indicator.set_menu(self.menu)
        self.indicator.set_secondary_activate_target(show_item)

        signal.signal(signal.SIGTERM, self.quit_indicator)
        signal.signal(signal.SIGINT, self.quit_indicator)
        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh)

    @staticmethod
    def _disabled_item(label):
        item = Gtk.MenuItem(label=label)
        item.set_sensitive(False)
        return item

    @staticmethod
    def _action_item(label, callback):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", callback)
        return item

    @staticmethod
    def _request_json(url, method="GET", data=None, timeout=2):
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}

    def refresh(self, *_args):
        if self.refresh_active:
            return True
        self.refresh_active = True
        threading.Thread(target=self._load_status, daemon=True).start()
        return True

    def _load_status(self):
        running = False
        current_node = "-"
        try:
            group = self._request_json(f"{CORE_API}/proxies/{GROUP}")
            with socket.create_connection(("127.0.0.1", MIXED_PORT), timeout=1):
                pass
            running = True
            current_node = group.get("now") or "-"
        except (OSError, ValueError, urllib.error.URLError):
            pass
        GLib.idle_add(self._apply_status, running, current_node)

    def _apply_status(self, running, current_node):
        self.running = running
        self.current_node = current_node
        self.refresh_active = False
        if running:
            self.indicator.set_icon_full("network-vpn-symbolic", "Tyty VPN 正在运行")
            self.indicator.set_title(f"Tyty - {self.current_node}")
            self.status_item.set_label("状态：运行中")
            self.node_item.set_label(f"当前节点：{self.current_node}")
        else:
            self.indicator.set_icon_full("network-offline-symbolic", "Tyty VPN 未连接")
            self.indicator.set_title("Tyty - 未连接")
            self.status_item.set_label("状态：未连接")
            self.node_item.set_label("当前节点：-")
        self._update_window()
        return False

    def show_window(self, *_args):
        if self.window is None:
            self.window = Gtk.Window(title="Tyty VPN 状态")
            self.window.set_default_size(420, 240)
            self.window.set_resizable(False)
            self.window.set_position(Gtk.WindowPosition.CENTER)
            self.window.connect("delete-event", self._hide_window)

            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            outer.set_border_width(20)
            self.window.add(outer)

            title = Gtk.Label()
            title.set_markup("<span size='x-large' weight='bold'>Tyty VPN</span>")
            title.set_xalign(0)
            outer.pack_start(title, False, False, 0)

            grid = Gtk.Grid(column_spacing=18, row_spacing=12)
            outer.pack_start(grid, True, True, 0)
            self.status_value = self._grid_row(grid, 0, "运行状态")
            self.node_value = self._grid_row(grid, 1, "当前节点")
            self._grid_row(grid, 2, "代理地址", f"127.0.0.1:{MIXED_PORT}")
            self._grid_row(grid, 3, "节点管理", WEBUI_URL)

            actions = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
            actions.set_layout(Gtk.ButtonBoxStyle.END)
            actions.set_spacing(8)
            outer.pack_start(actions, False, False, 0)
            actions.add(self._button("刷新", self.refresh))
            actions.add(self._button("测试连接", self.test_connection))
            actions.add(self._button("打开 WebUI", self.open_webui))
            actions.add(self._button("关闭", self._hide_window))

        self.window.show_all()
        self.window.present()
        self.refresh()

    @staticmethod
    def _grid_row(grid, row, title, value=""):
        key = Gtk.Label(label=title)
        key.set_xalign(0)
        key.get_style_context().add_class("dim-label")
        result = Gtk.Label(label=value)
        result.set_xalign(0)
        result.set_selectable(True)
        result.set_ellipsize(Pango.EllipsizeMode.END)
        result.set_max_width_chars(38)
        grid.attach(key, 0, row, 1, 1)
        grid.attach(result, 1, row, 1, 1)
        return result

    @staticmethod
    def _button(label, callback):
        button = Gtk.Button(label=label)
        button.connect("clicked", callback)
        return button

    def _update_window(self):
        if self.status_value is not None:
            self.status_value.set_text("运行中" if self.running else "未连接")
            self.node_value.set_text(self.current_node)

    def _hide_window(self, *_args):
        if self.window is not None:
            self.window.hide()
        return True

    def open_webui(self, *_args):
        subprocess.Popen(
            ["xdg-open", WEBUI_URL],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_connection(self, *_args):
        if self.test_active:
            return
        self.test_active = True
        self.test_item.set_sensitive(False)
        threading.Thread(target=self._run_connection_test, daemon=True).start()

    def _run_connection_test(self):
        success = False
        detail = "连接失败"
        is_error = False
        try:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": PROXY_URL, "https": PROXY_URL})
            )
            request = urllib.request.Request("https://www.google.com/generate_204")
            with opener.open(request, timeout=15) as response:
                success = response.status == 204
            detail = "连接正常" if success else "连接失败"
            is_error = not success
        except (OSError, urllib.error.URLError) as error:
            detail = f"连接失败：{error}"
            is_error = True
        GLib.idle_add(self._show_test_result, detail, is_error)

    def _show_test_result(self, detail, is_error):
        self.test_active = False
        self.test_item.set_sensitive(True)
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.ERROR if is_error else Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="代理连接测试",
        )
        dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()
        return False

    def stop_proxy(self, *_args):
        subprocess.Popen(
            [os.path.join(ROOT, "stop.sh")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        Gtk.main_quit()

    @staticmethod
    def quit_indicator(*_args):
        Gtk.main_quit()


if __name__ == "__main__":
    TytyIndicator()
    Gtk.main()
