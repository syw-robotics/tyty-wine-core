#!/usr/bin/env python3
import json
import os
import signal
import shutil
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
MODES = (("rule", "规则模式"), ("global", "全局代理"))
MODE_LABELS = dict(MODES)


class TytyIndicator:
    def __init__(self):
        self.current_node = "-"
        self.mode = "-"
        self.running = False
        self.proxy_enabled = False
        self.window = None
        self.status_value = None
        self.node_value = None
        self.mode_value = None
        self.mode_combo = None
        self.toggle_button = None
        self.refresh_active = False
        self.test_active = False
        self.toggle_active = False
        self.mode_active = False
        self.syncing_mode = False
        self.gsettings_available = shutil.which("gsettings") is not None

        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "tyty-wine-core",
            "network-vpn-symbolic",
            AyatanaAppIndicator3.IndicatorCategory.SYSTEM_SERVICES,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()
        self.status_item = self._disabled_item("状态：正在连接")
        self.node_item = self._disabled_item("当前节点：-")
        self.mode_item = self._disabled_item("运行模式：-")
        self.menu.append(self.status_item)
        self.menu.append(self.node_item)
        self.menu.append(self.mode_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        show_item = self._action_item("打开状态窗口", self.show_window)
        self.menu.append(show_item)
        self.menu.append(self._action_item("打开 WebUI", self.open_webui))
        self.test_item = self._action_item("测试连接", self.test_connection)
        self.menu.append(self.test_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        self.mode_menu_items = {}
        mode_group = None
        for mode, label in MODES:
            item = Gtk.RadioMenuItem.new_with_label(mode_group, label)
            item.connect("toggled", self.change_mode, mode)
            item.set_sensitive(False)
            self.menu.append(item)
            self.mode_menu_items[mode] = item
            mode_group = item.get_group()
        self.menu.append(Gtk.SeparatorMenuItem())
        self.toggle_item = self._action_item("暂停代理", self.toggle_proxy)
        self.toggle_item.set_sensitive(False)
        self.menu.append(self.toggle_item)
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
        mode = "-"
        try:
            group = self._request_json(f"{CORE_API}/proxies/{GROUP}")
            with socket.create_connection(("127.0.0.1", MIXED_PORT), timeout=1):
                pass
            running = True
            current_node = group.get("now") or "-"
            try:
                mode = self._request_json(f"{CORE_API}/configs").get("mode") or "rule"
            except (OSError, ValueError, urllib.error.URLError):
                mode = "-"
        except (OSError, ValueError, urllib.error.URLError):
            pass
        proxy_enabled = self._system_proxy_enabled()
        GLib.idle_add(self._apply_status, running, current_node, mode, proxy_enabled)

    def _apply_status(self, running, current_node, mode, proxy_enabled):
        self.running = running
        self.current_node = current_node
        self.mode = mode
        self.proxy_enabled = proxy_enabled
        self.refresh_active = False
        if running:
            tooltip = "Tyty VPN 正在运行" if proxy_enabled else "Tyty VPN 已暂停"
            self.indicator.set_icon_full("network-vpn-symbolic", tooltip)
            self.indicator.set_title(f"Tyty - {self.current_node}")
            status = "运行中" if proxy_enabled else "已暂停"
            self.status_item.set_label(f"状态：{status}")
            self.node_item.set_label(f"当前节点：{self.current_node}")
            self.mode_item.set_label(f"运行模式：{MODE_LABELS.get(self.mode, self.mode)}")
        else:
            self.indicator.set_icon_full("network-offline-symbolic", "Tyty VPN 未连接")
            self.indicator.set_title("Tyty - 未连接")
            self.status_item.set_label("状态：未连接")
            self.node_item.set_label("当前节点：-")
            self.mode_item.set_label("运行模式：-")
        self.syncing_mode = True
        for name, item in self.mode_menu_items.items():
            item.set_active(name == self.mode)
            item.set_sensitive(running and not self.mode_active)
        self.syncing_mode = False
        self.toggle_item.set_label("暂停代理" if proxy_enabled else "打开代理")
        self.toggle_item.set_sensitive(
            self.gsettings_available and running and not self.toggle_active
        )
        self._update_window()
        return False

    def _system_proxy_enabled(self):
        if not self.gsettings_available:
            return False
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.system.proxy", "mode"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.stdout.strip().strip("'") == "manual"
        except (OSError, subprocess.SubprocessError):
            return False

    def show_window(self, *_args):
        if self.window is None:
            self.window = Gtk.Window(title="Tyty VPN 状态")
            self.window.set_default_size(560, 280)
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
            self.mode_value = self._grid_row(grid, 2, "运行模式")
            self.mode_combo = Gtk.ComboBoxText()
            for mode, label in MODES:
                self.mode_combo.append(mode, label)
            self.mode_combo.connect("changed", self.change_mode_combo)
            grid.attach(self.mode_combo, 2, 2, 1, 1)
            self._grid_row(grid, 3, "代理地址", f"127.0.0.1:{MIXED_PORT}")
            self._grid_row(grid, 4, "节点管理", WEBUI_URL)

            actions = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
            actions.set_layout(Gtk.ButtonBoxStyle.END)
            actions.set_spacing(8)
            outer.pack_start(actions, False, False, 0)
            actions.add(self._button("刷新", self.refresh))
            actions.add(self._button("测试连接", self.test_connection))
            actions.add(self._button("打开 WebUI", self.open_webui))
            self.toggle_button = self._button("暂停代理", self.toggle_proxy)
            actions.add(self.toggle_button)
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
            if not self.running:
                status = "未连接"
            else:
                status = "运行中" if self.proxy_enabled else "已暂停"
            self.status_value.set_text(status)
            self.node_value.set_text(self.current_node)
        if self.mode_value is not None:
            self.mode_value.set_text(MODE_LABELS.get(self.mode, self.mode))
        if self.mode_combo is not None:
            self.syncing_mode = True
            self.mode_combo.set_active_id(self.mode if self.mode in MODE_LABELS else None)
            self.mode_combo.set_sensitive(self.running and not self.mode_active)
            self.syncing_mode = False
        if self.toggle_button is not None:
            self.toggle_button.set_label(
                "暂停代理" if self.proxy_enabled else "打开代理"
            )
            self.toggle_button.set_sensitive(
                self.gsettings_available and self.running and not self.toggle_active
            )

    def _hide_window(self, *_args):
        if self.window is not None:
            self.window.hide()
        return True

    def open_webui(self, *_args):
        subprocess.Popen(
            [os.path.join(ROOT, "open-webui.sh")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def toggle_proxy(self, *_args):
        if self.toggle_active or not self.running or not self.gsettings_available:
            return
        self.toggle_active = True
        self.toggle_item.set_sensitive(False)
        if self.toggle_button is not None:
            self.toggle_button.set_sensitive(False)
        threading.Thread(target=self._set_proxy_enabled, daemon=True).start()

    def _set_proxy_enabled(self):
        enable = not self.proxy_enabled
        commands = []
        if enable:
            commands = [
                ["gsettings", "set", "org.gnome.system.proxy.http", "host", "127.0.0.1"],
                ["gsettings", "set", "org.gnome.system.proxy.http", "port", str(MIXED_PORT)],
                ["gsettings", "set", "org.gnome.system.proxy.https", "host", "127.0.0.1"],
                ["gsettings", "set", "org.gnome.system.proxy.https", "port", str(MIXED_PORT)],
                ["gsettings", "set", "org.gnome.system.proxy.socks", "host", "127.0.0.1"],
                ["gsettings", "set", "org.gnome.system.proxy.socks", "port", str(MIXED_PORT)],
            ]
        commands.append([
            "gsettings", "set", "org.gnome.system.proxy", "mode",
            "manual" if enable else "none",
        ])
        try:
            for command in commands:
                subprocess.run(command, check=True, timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass
        GLib.idle_add(self._finish_toggle)

    def change_mode(self, item, mode):
        if not item.get_active() or self.syncing_mode:
            return
        self._change_mode(mode)

    def change_mode_combo(self, combo):
        if self.syncing_mode:
            return
        mode = combo.get_active_id()
        if mode is not None:
            self._change_mode(mode)

    def _change_mode(self, mode):
        if self.mode_active or not self.running or mode == self.mode:
            return
        self.mode_active = True
        for item in self.mode_menu_items.values():
            item.set_sensitive(False)
        if self.mode_combo is not None:
            self.mode_combo.set_sensitive(False)
        threading.Thread(target=self._set_mode, args=(mode,), daemon=True).start()

    def _set_mode(self, mode):
        try:
            self._request_json(f"{CORE_API}/configs", method="PATCH", data={"mode": mode})
        except (OSError, ValueError, urllib.error.URLError):
            pass
        GLib.idle_add(self._finish_mode)

    def _finish_mode(self):
        self.mode_active = False
        self.refresh()
        return False

    def _finish_toggle(self):
        self.toggle_active = False
        self.refresh()
        return False

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
