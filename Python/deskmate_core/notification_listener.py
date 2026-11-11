"""
DeskMate Pro - 通知监听模块

负责：
  1. IMAP 定时检查新邮件；
  2. 日历接口预留（暂未实现）。

检测到新消息后，通过 on_new_message 回调交给主程序：
  - 发送 JSON 指令给 Arduino；
  - 弹出系统通知。
"""

import email
import imaplib
import threading
import time
from email.header import decode_header
from typing import Callable, Dict, Optional, Set

from deskmate_core import config


class NotificationListener:
    """邮件/日历监听器。"""

    def __init__(self, on_new_message: Optional[Callable[[Dict], None]] = None):
        """
        参数：
            on_new_message: 回调函数，参数为 {"src","title","time","id"}。
        """
        self.on_new_message = on_new_message
        self._seen_ids: Set[str] = set()
        self._next_id = 1
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动后台监听线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="NotificationListener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止监听线程。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    # ---------------------- 后台循环 ----------------------
    def _run(self) -> None:
        while self._running:
            if config.IMAP_ENABLED:
                try:
                    self._check_imap_once()
                except Exception as exc:
                    print(f"[NotificationListener] IMAP 检查失败: {exc}")
            # 日历扩展点：在这里调用 _check_calendar_once()
            time.sleep(config.IMAP_CHECK_INTERVAL)

    # ---------------------- IMAP ----------------------
    def _check_imap_once(self) -> None:
        """连接 IMAP 并查找未读邮件。"""
        if config.IMAP_USE_SSL:
            conn = imaplib.IMAP4_SSL(config.IMAP_SERVER, config.IMAP_PORT)
        else:
            conn = imaplib.IMAP4(config.IMAP_SERVER, config.IMAP_PORT)

        try:
            conn.login(config.IMAP_USER, config.IMAP_PASSWORD)
            conn.select("INBOX", readonly=True)
            typ, data = conn.search(None, "UNSEEN")
            if typ != "OK" or not data or not data[0]:
                return
            ids = data[0].split()
            # 只处理最近 5 封，避免一次处理过多
            for mid in ids[-5:]:
                mid_str = mid.decode()
                if mid_str in self._seen_ids:
                    continue
                self._seen_ids.add(mid_str)
                msg = self._fetch_message(conn, mid_str)
                if msg:
                    self._dispatch(msg)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _fetch_message(self, conn: imaplib.IMAP4, mid: str) -> Optional[Dict]:
        """读取单封邮件的标题/发件人/时间。"""
        try:
            typ, msg_data = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK":
                return None
            raw = msg_data[0][1]
            parser = email.parser.BytesParser()
            msg = parser.parsebytes(raw)
            subject = self._decode_mime(msg.get("Subject", "无主题"))
            sender = self._decode_mime(msg.get("From", "未知发件人"))
            title = f"{sender}: {subject}"
            date = msg.get("Date", "")
            # 尽量只保留 HH:MM，便于 Arduino OLED 显示
            short_time = time.strftime("%H:%M")
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(date)
                if dt:
                    short_time = dt.strftime("%H:%M")
            except Exception:
                pass
            return {"src": "email", "title": title[:80], "time": short_time}
        except Exception as exc:
            print(f"[NotificationListener] 解析邮件失败: {exc}")
            return None

    @staticmethod
    def _decode_mime(value: str) -> str:
        """解码 MIME 编码的邮件头。"""
        if not value:
            return ""
        parts = decode_header(value)
        out = []
        for text, charset in parts:
            if isinstance(text, bytes):
                try:
                    out.append(text.decode(charset or "utf-8", errors="ignore"))
                except Exception:
                    out.append(text.decode("utf-8", errors="ignore"))
            else:
                out.append(text)
        return "".join(out)

    # ---------------------- 分发 ----------------------
    def _dispatch(self, msg: Dict) -> None:
        """为消息补充时间/ID 并调用回调。"""
        if "time" not in msg or not msg["time"]:
            msg["time"] = time.strftime("%H:%M")
        msg["id"] = self._next_id
        self._next_id += 1
        if self.on_new_message:
            try:
                self.on_new_message(msg)
            except Exception as exc:
                print(f"[NotificationListener] 新消息回调异常: {exc}")

    # ---------------------- 日历扩展（预留） ----------------------
    def _check_calendar_once(self) -> None:
        """
        日历同步预留接口。
        未来可在此实现：查询未来 24 小时日程，对比已提醒集合，发现新日程后调用：
            self._dispatch({"src": "calendar", "title": "会议邀请", "time": "14:00"})
        """
        pass
