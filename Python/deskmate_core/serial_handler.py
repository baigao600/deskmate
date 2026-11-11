"""
DeskMate Pro - 串口通信模块

负责：
  1. 后台线程读取 Arduino 发来的按行 JSON；
  2. 自动重连；
  3. 提供 send_command 向 Arduino 发送 JSON 指令。
"""

import json
import threading
import time
from typing import Callable, Dict, Optional, List

import serial
import serial.tools.list_ports

from deskmate_core import config


class SerialHandler:
    """串口读写与重连管理。"""

    def __init__(self,
                 port: Optional[str] = None,
                 baud: int = 115200,
                 timeout: float = 1.0,
                 on_line: Optional[Callable[[Dict], None]] = None):
        """
        参数：
            port:     串口名；为 None 时自动探测。
            baud:     波特率。
            timeout:  读取超时（秒）。
            on_line:  解析出 JSON 对象后的回调函数。
        """
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.on_line = on_line
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ---------------------- 生命周期 ----------------------
    def start(self) -> None:
        """启动后台读取线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="SerialReader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止后台线程并关闭串口。"""
        self._running = False
        self._close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    # ---------------------- 发送 ----------------------
    def send_command(self, payload: Dict) -> bool:
        """
        将字典编码为 JSON 并发送（自动加换行符）。
        返回是否发送成功。
        """
        try:
            line = json.dumps(payload, ensure_ascii=False) + "\n"
            data = line.encode("utf-8")
            with self._lock:
                if self._ser is None or not self._ser.is_open:
                    return False
                self._ser.write(data)
            return True
        except Exception as exc:
            print(f"[SerialHandler] 发送失败: {exc}")
            return False

    # ---------------------- 内部实现 ----------------------
    def _run(self) -> None:
        """读取线程：负责打开、循环读取、异常后重连。"""
        while self._running:
            if self._ser is None or not self._ser.is_open:
                if not self._connect():
                    time.sleep(config.SERIAL_RECONNECT_INTERVAL)
                    continue
            try:
                line = self._ser.readline()
            except (serial.SerialException, OSError) as exc:
                print(f"[SerialHandler] 读取异常，准备重连: {exc}")
                self._close()
                time.sleep(config.SERIAL_RECONNECT_INTERVAL)
                continue

            if not line:
                continue
            try:
                text = line.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if not text:
                continue
            self._handle_line(text)

    def _connect(self) -> bool:
        """尝试打开串口。"""
        target = self.port or self._autodetect_port()
        if not target:
            return False
        try:
            with self._lock:
                self._ser = serial.Serial(target, self.baud, timeout=self.timeout)
            print(f"[SerialHandler] 已连接串口: {target}")
            return True
        except (serial.SerialException, OSError) as exc:
            print(f"[SerialHandler] 打开串口失败 {target}: {exc}")
            self._ser = None
            return False

    def _close(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

    @staticmethod
    def _autodetect_port() -> Optional[str]:
        """返回第一个可用串口，若没有则返回 None。"""
        ports: List[str] = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            print("[SerialHandler] 未检测到可用串口，请确认 Arduino 已连接。")
            return None
        print(f"[SerialHandler] 自动选择串口: {ports[0]}")
        return ports[0]

    def _handle_line(self, text: str) -> None:
        """解析单行 JSON 并回调。"""
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            print(f"[SerialHandler] 忽略非 JSON 行: {text[:80]}")
            return
        if not isinstance(obj, dict):
            return
        if self.on_line:
            try:
                self.on_line(obj)
            except Exception as exc:
                print(f"[SerialHandler] 事件回调异常: {exc}")
