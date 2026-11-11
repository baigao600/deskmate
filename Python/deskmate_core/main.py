"""
DeskMate Pro - 主程序入口

初始化各模块并保持运行：
  1. SerialHandler       串口收发
  2. SystemController    系统控制
  3. NotificationListener 邮件/日历监听
  4. OSDManager          OSD 显示（主线程运行 Tk 主循环）
"""

import time
import os
import tempfile
import threading
from typing import Dict

from deskmate_core import config
from deskmate_core.serial_handler import SerialHandler
from deskmate_core.system_controller import SystemController
from deskmate_core.notification_listener import NotificationListener
from deskmate_core.osd_manager import OSDManager


APP_LOG = os.path.join(tempfile.gettempdir(), "DeskMatePro_app.log")


def _app_log(message: str) -> None:
    try:
        with open(APP_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


class DeskMateApp:
    """应用协调器：把串口事件分发到系统控制和 OSD。"""

    def __init__(self):
        self.system = SystemController()
        self.osd = OSDManager()
        self.serial = SerialHandler(
            port=config.SERIAL_PORT,
            baud=config.SERIAL_BAUD,
            timeout=config.SERIAL_TIMEOUT,
            on_line=self._on_serial_event,
        )
        self.notifier = NotificationListener(on_new_message=self._on_new_message)
        self.wechat = None
        if config.WECHAT_ENABLED:
            try:
                from deskmate_core.wechat_listener import WeChatListener
            except ModuleNotFoundError as exc:
                if exc.name != "deskmate_core.wechat_listener":
                    raise
            else:
                self.wechat = WeChatListener(
                    on_new_message=self._on_new_message,
                    on_preload_message=self._on_preload_message,
                )

        self.current_mode = "control"
        self.dnd = False
        self._running = False
        self._pending_preload: list = []
        self._preload_lock = threading.Lock()

        # 绑定 OSD 清空按钮回调
        self.osd.on_clear_requested = self._clear_messages_from_osd

    # ======================= 启动 =======================
    def start(self) -> None:
        """启动后台模块，然后进入 OSD 主循环。"""
        print("DeskMate Pro 启动中...")
        _app_log("APP_START")
        self._running = True
        self.serial.start()
        self.notifier.start()
        if self.wechat is not None:
            self.wechat.start()
        self._start_preload_flusher()
        # 启动后把当前系统音量同步给 Arduino，保证表盘/舵机一致
        time.sleep(0.5)
        self._send({"cmd": "sync_volume", "val": self.system.get_volume()})
        if config.SELF_TEST_ON_START:
            def _send_selftest():
                self._send({"cmd": "selftest"})
                _app_log("SELFTEST_CMD_SENT")
            threading.Timer(6.0, _send_selftest).start()
        try:
            self.osd.start()   # 阻塞在 Tk 主循环
        finally:
            self._running = False
            self.serial.stop()
            self.notifier.stop()
            if self.wechat is not None:
                self.wechat.stop()

    # ======================= 串口事件分发 =======================
    def _on_serial_event(self, event: Dict) -> None:
        evt = event.get("evt")
        _app_log(f"EVT {event}")
        if evt == "volume":
            val = int(event.get("val", 50))
            self.system.set_volume(val)
            self.osd.show_volume(val)
        elif evt == "btn":
            self._handle_button(event.get("act", ""))
        elif evt == "tilt":
            direction = event.get("dir", "")
            try:
                self.system.switch_virtual_desktop(direction)
                _app_log(f"TILT_OK {direction}")
            except Exception as exc:
                _app_log(f"TILT_ERR {direction}: {exc}")
            self.osd.show_desktop_animation(direction)
        elif evt == "knock":
            try:
                path = self.system.take_screenshot()
                _app_log(f"KNOCK_SHOT {'OK ' + str(path) if path else 'FAIL'}")
                if path:
                    self.osd.flash_screen()
                    self.osd.show_notification("DeskMate 截图", path)
            except Exception as exc:
                _app_log(f"KNOCK_ERR {exc}")
        elif evt == "msg_select":
            self.osd.set_selected(int(event.get("index", 0)))
        elif evt == "msg_open":
            src = event.get("src", "")
            title = event.get("title", "")
            mid = event.get("id")
            self.osd.remove_by_id(mid)
            self.osd.show_notification(f"打开消息 [{src}]", title)
        elif evt == "mode":
            mode = event.get("mode", "control")
            self.current_mode = mode
            self.osd.set_mode(mode)
            _app_log(f"MODE_SYNC {mode}")
            # 回确认指令
            self._send({"cmd": "set_mode", "mode": mode})

    def _handle_button(self, act: str) -> None:
        """处理按钮动作。Arduino 已按模式做了映射，此处只负责系统操作。"""
        if self.current_mode == "control":
            if act == "single":
                self.system.media_play_pause()
            elif act == "double":
                self.system.media_next()
            elif act == "long":
                self.system.toggle_mute()
        else:
            # 消息模式：long=免打扰，double=清除所有未读；single 会由 Arduino
            # 直接发送 msg_open，而不是 btn 事件。
            if act == "double":
                self.osd.clear_messages()
            elif act == "long":
                self.dnd = not self.dnd
                self.osd.set_dnd(self.dnd)

    # ======================= 新消息 =======================
    def _on_new_message(self, msg: Dict) -> None:
        """收到新邮件/日历事件后，通知 Arduino 并更新 OSD。"""
        src = msg.get("src", "email")
        title = msg.get("title", "无标题")
        oled_text = msg.get("content") or title   # OLED 只显示正文，不显示发件人
        time_str = msg.get("time", time.strftime("%H:%M"))
        mid = int(msg.get("id", 0))

        self._send({
            "cmd": "new_msg",
            "src": src,
            "title": oled_text,
            "time": time_str,
            "id": mid,
        })
        self.osd.add_message(src, title, time_str, mid)
        self.osd.show_notification(f"新消息 ({src})", title)

    def _on_preload_message(self, msg: Dict) -> None:
        """启动时预载微信未读消息：静默入列表，不响铃、不弹通知。"""
        src = msg.get("src", "wechat")
        title = msg.get("title", "")
        oled_text = msg.get("content") or title   # OLED 只显示正文
        time_str = msg.get("time", time.strftime("%H:%M"))
        mid = int(msg.get("id", 0))

        payload = {
            "cmd": "load_msg",
            "src": src,
            "title": oled_text,
            "time": time_str,
            "id": mid,
        }
        self.osd.add_message(src, title, time_str, mid)
        # 串口在启动早期可能尚未连接；失败则放入待发队列，稍后自动重发
        if not self._send(payload):
            with self._preload_lock:
                self._pending_preload.append(payload)

    def _start_preload_flusher(self) -> None:
        """后台线程定时重发尚未送出的预载消息，直到串口连上。"""
        def _loop():
            while self._running:
                time.sleep(0.5)
                self._flush_preload()

        threading.Thread(target=_loop, name="PreloadFlusher", daemon=True).start()

    def _flush_preload(self) -> None:
        """尝试把待发的预载消息发送给 Arduino。"""
        if not self._pending_preload:
            return
        with self._preload_lock:
            pending = self._pending_preload
            self._pending_preload = []
        still = [p for p in pending if not self._send(p)]
        if still:
            with self._preload_lock:
                self._pending_preload = still + self._pending_preload

    # ======================= 辅助 =======================
    def _send(self, payload: Dict) -> bool:
        return self.serial.send_command(payload)

    def _clear_messages_from_osd(self) -> None:
        """侧边栏清空按钮：向 Arduino 发送清除指令。"""
        self._send({"cmd": "clear_msgs"})
        self.osd.clear_messages()


def run() -> None:
    """供 entry 脚本调用的入口函数。"""
    app = DeskMateApp()
    app.start()


if __name__ == "__main__":
    run()
