"""
DeskMate Pro - 系统控制模块

负责音量、媒体键、虚拟桌面切换、截屏等操作系统级操作。
所有可能失败的调用都做了异常捕获，单个错误不会导致程序崩溃。
"""

import os
import platform
import subprocess
import time
from typing import Optional

from deskmate_core import config


class SystemController:
    """跨平台系统控制。"""

    def __init__(self):
        self.system = platform.system().lower()  # "windows" / "darwin" / "linux"
        self._volume: Optional[object] = None     # Windows 下保存 pycaw 音量对象
        self._audio_device = None
        self._init_volume()

    # ---------------------- 音量 ----------------------
    def _init_volume(self) -> None:
        """初始化音量控制；Windows 使用 pycaw，macOS 使用 osascript。"""
        if self.system == "windows":
            try:
                from pycaw.pycaw import AudioUtilities

                devices = AudioUtilities.GetSpeakers()
                # 新版 pycaw（2025+）直接提供 EndpointVolume 接口
                if hasattr(devices, "EndpointVolume"):
                    self._volume = devices.EndpointVolume
                else:
                    # 旧版 pycaw 需要通过 Activate 获取
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import IAudioEndpointVolume
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    self._volume = cast(interface, POINTER(IAudioEndpointVolume))
                print("[SystemController] pycaw 音量控制已初始化")
            except Exception as exc:
                print(f"[SystemController] pycaw 初始化失败（音量功能可能不可用）: {exc}")
                self._volume = None

    def get_volume(self) -> int:
        """获取当前系统音量（0~100）。"""
        try:
            if self.system == "windows" and self._volume is not None:
                vol = self._volume.GetMasterVolumeLevelScalar()
                return int(round(vol * 100))
            if self.system == "darwin":
                out = subprocess.check_output(
                    ["osascript", "-e", "output volume of (get volume settings)"],
                    stderr=subprocess.DEVNULL).decode().strip()
                return int(out)
        except Exception as exc:
            print(f"[SystemController] 获取音量失败: {exc}")
        return 50

    def set_volume(self, value: int) -> None:
        """设置系统音量为 0~100。"""
        value = max(0, min(100, int(value)))
        try:
            if self.system == "windows" and self._volume is not None:
                self._volume.SetMasterVolumeLevelScalar(value / 100.0, None)
            elif self.system == "darwin":
                subprocess.run(["osascript", "-e", f"set volume output volume {value}"],
                               check=False)
        except Exception as exc:
            print(f"[SystemController] 设置音量失败: {exc}")

    def toggle_mute(self) -> None:
        """切换静音状态。"""
        try:
            if self.system == "windows" and self._volume is not None:
                self._volume.SetMute(not self._volume.GetMute(), None)
            elif self.system == "darwin":
                subprocess.run(
                    ["osascript", "-e",
                     "set volume output muted not (output muted of (get volume settings))"],
                    check=False)
        except Exception as exc:
            print(f"[SystemController] 静音切换失败: {exc}")

    # ---------------------- 媒体控制 ----------------------
    # 媒体键在两个库里的名称不一致，这里统一映射：
    #   keyboard 使用 "play/pause" / "next track" 等（带分隔符）
    #   pyautogui 使用 "playpause" / "nexttrack" 等（无分隔符）
    _MEDIA_KEY_MAP = {
        "playpause": ("play/pause", "playpause"),
        "nexttrack": ("next track", "nexttrack"),
        "prevtrack": ("previous track", "prevtrack"),
    }

    def media_play_pause(self) -> None:
        """播放/暂停。"""
        self._send_key("playpause")

    def media_next(self) -> None:
        """下一曲。"""
        self._send_key("nexttrack")

    def _send_key(self, key: str) -> None:
        """发送媒体键，优先使用 keyboard，回退到 pyautogui。"""
        kb_name, pa_name = self._MEDIA_KEY_MAP.get(key, (key, key))
        try:
            import keyboard
            keyboard.press_and_release(kb_name)
            return
        except Exception:
            pass
        try:
            import pyautogui
            pyautogui.FAILSAFE = False   # 常驻后台工具，避免鼠标在屏幕角落时被误拦截
            pyautogui.press(pa_name)
        except Exception as exc:
            print(f"[SystemController] 媒体键 {key} 失败: {exc}")

    # ---------------------- 虚拟桌面切换 ----------------------
    def switch_virtual_desktop(self, direction: str) -> None:
        """
        切换虚拟桌面。
        direction: "left" 或 "right"
        Windows 使用 Win+Ctrl+Left/Right；macOS 使用 Ctrl+Left/Right。
        """
        direction = direction.lower()
        if direction not in ("left", "right"):
            return
        try:
            if self.system == "windows":
                # 优先 keyboard，更可靠
                try:
                    import keyboard
                    keyboard.press_and_release(f"ctrl+windows+{direction}")
                    return
                except Exception:
                    pass
                import pyautogui
                pyautogui.hotkey("ctrl", "win", direction)
            elif self.system == "darwin":
                import pyautogui
                pyautogui.hotkey("ctrl", direction)
        except Exception as exc:
            print(f"[SystemController] 虚拟桌面切换失败: {exc}")

    # ---------------------- 截屏 ----------------------
    def take_screenshot(self) -> Optional[str]:
        """
        截取全屏并保存到桌面，返回文件路径。
        失败返回 None。
        """
        filename = f"DeskMate_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(config.screenshot_dir(), filename)
        try:
            if self.system == "windows":
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(path, "PNG")
            elif self.system == "darwin":
                subprocess.run(["screencapture", "-x", path], check=True)
            else:
                # Linux 可安装 scrot 后使用；这里给出占位
                subprocess.run(["scrot", path], check=True)
            print(f"[SystemController] 截图已保存: {path}")
            return path
        except Exception as exc:
            print(f"[SystemController] 截屏失败: {exc}")
            return None
