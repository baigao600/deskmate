"""
DeskMate Pro - OSD 界面模块（tkinter）

包含四个无边框、半透明、置顶窗口：
  1. 音量表盘（右上角，圆形指针）
  2. 消息侧边栏（右侧滑入，列出未读消息）
  3. 状态指示器（右下角，模式/未读数/免打扰）
  4. 虚拟桌面切换动画（屏幕中央左右箭头）

其中音量表盘、消息侧边栏、状态指示器均支持鼠标拖动。
为保证线程安全，后台线程调用公开方法时会把操作放入队列，由 Tk 主循环统一执行。
"""

import math
import queue
import tkinter as tk
from typing import Dict, List

from deskmate_core import config


class OSDManager:
    """OSD 显示管理。"""

    # 主题配色
    BG = "#0e0e15"
    CARD = "#171720"
    CARD_BORDER = "#2b2b3a"
    TEXT = "#f2f2f7"
    MUTED = "#8b8b98"
    ACCENT = "#5aa9ff"

    SRC_COLORS = {
        "email": "#4da3ff",
        "calendar": "#ffb347",
        "wechat": "#4cd964",
    }

    def __init__(self):
        self.root: tk.Tk = None
        self.queue: "queue.Queue" = queue.Queue()

        self.volume_win: tk.Toplevel = None
        self.volume_canvas: tk.Canvas = None
        self.volume_value = 50

        self.sidebar_win: tk.Toplevel = None
        self.sidebar_canvas: tk.Canvas = None
        self.sidebar_frame: tk.Frame = None
        self.sidebar_items: List[tk.Widget] = []

        self.status_win: tk.Toplevel = None
        self.status_canvas: tk.Canvas = None

        self.desktop_win: tk.Toplevel = None
        self.desktop_canvas: tk.Canvas = None

        self.current_mode = "control"
        self.dnd = False
        self.messages: List[Dict] = []
        self.selected_index = 0

        self._volume_hide_job = None
        self._desktop_hide_job = None
        self._sidebar_hide_job = None
        self._fade_jobs = {}

    # ======================= 生命周期 =======================
    def start(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self._create_volume_window()
        self._create_sidebar_window()
        self._create_status_window()
        self._create_desktop_window()
        self.root.after(50, self._drain_queue)
        self.root.mainloop()

    def stop(self) -> None:
        if self.root:
            self.root.after(0, self.root.destroy)

    # ======================= 公开接口（线程安全） =======================
    def show_volume(self, value: int) -> None:
        self._enqueue("_show_volume", value)

    def set_mode(self, mode: str) -> None:
        self._enqueue("_set_mode", mode)

    def set_dnd(self, enabled: bool) -> None:
        self._enqueue("_set_dnd", enabled)

    def add_message(self, src: str, title: str, time_str: str, mid: int = 0) -> None:
        self._enqueue("_add_message", src, title, time_str, mid)

    def remove_selected(self) -> None:
        self._enqueue("_remove_selected")

    def remove_by_id(self, mid: int) -> None:
        self._enqueue("_remove_by_id", mid)

    def clear_messages(self) -> None:
        self._enqueue("_clear_messages")

    def set_selected(self, index: int) -> None:
        self._enqueue("_set_selected", index)

    def show_notification(self, title: str, message: str) -> None:
        self._enqueue("_show_notification", title, message)

    def show_desktop_animation(self, direction: str) -> None:
        self._enqueue("_show_desktop_animation", direction)

    def flash_screen(self) -> None:
        self._enqueue("_flash_screen")

    # ======================= 队列处理 =======================
    def _enqueue(self, name: str, *args, **kwargs) -> None:
        self.queue.put((name, args, kwargs))

    def _drain_queue(self) -> None:
        try:
            while True:
                name, args, kwargs = self.queue.get_nowait()
                handler = getattr(self, name, None)
                if handler:
                    try:
                        handler(*args, **kwargs)
                    except Exception as exc:
                        print(f"[OSDManager] 处理 {name} 失败: {exc}")
        except queue.Empty:
            pass
        if self.root:
            self.root.after(50, self._drain_queue)

    # ======================= 基础工具 =======================
    def _base_window(self, w: int, h: int, x: int, y: int) -> tk.Toplevel:
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", config.OSD_ALPHA)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.configure(bg=self.BG)
        win.withdraw()
        return win

    @staticmethod
    def _round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def _make_draggable(self, win: tk.Toplevel) -> None:
        """让窗口及其所有子组件支持鼠标拖动。"""
        offset = {"x": 0, "y": 0}

        def on_press(event):
            offset["x"] = event.x_root - win.winfo_x()
            offset["y"] = event.y_root - win.winfo_y()

        def on_drag(event):
            x = event.x_root - offset["x"]
            y = event.y_root - offset["y"]
            win.geometry(f"+{x}+{y}")

        def bind_recursive(widget):
            widget.bind("<ButtonPress-1>", on_press, add="+")
            widget.bind("<B1-Motion>", on_drag, add="+")
            for child in widget.winfo_children():
                bind_recursive(child)

        bind_recursive(win)

    # ======================= 音量表盘 =======================
    def _create_volume_window(self) -> None:
        w, h = 190, 216
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.volume_win = self._base_window(w, h, sw - w - 24, 24)
        self.volume_canvas = tk.Canvas(self.volume_win, width=w, height=h,
                                       bg=self.BG, highlightthickness=0)
        self.volume_canvas.pack(fill="both", expand=True)
        self._draw_volume(self.volume_value)
        self._make_draggable(self.volume_win)

    @staticmethod
    def _volume_color(t: float) -> str:
        # 0 -> 绿色，0.5 -> 黄色，1 -> 红色
        if t < 0.5:
            r = int(255 * t * 2)
            g = 255
            b = 82
        else:
            r = 255
            g = int(255 * (1 - (t - 0.5) * 2))
            b = 82
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw_volume(self, value: int) -> None:
        c = self.volume_canvas
        c.delete("all")
        w, h = 190, 216
        cx, cy, r = 95, 104, 66

        self._round_rect(c, 2, 2, w - 2, h - 2, 16,
                         fill=self.CARD, outline=self.CARD_BORDER, width=1)
        c.create_text(cx, 22, text="VOLUME", fill=self.MUTED,
                      font=("Segoe UI", 9, "bold"))

        # 表盘底
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      outline="#23232f", width=5, fill="#12121a")

        # 进度弧（渐变，从左侧 0 到右侧 100）
        arc_box = (cx - r + 9, cy - r + 9, cx + r - 9, cy + r - 9)
        segs = max(1, int(value * 1.8))
        for a in range(segs):
            t = a / 180.0
            start = 180 - a
            c.create_arc(arc_box, start=start, extent=-1, style=tk.ARC,
                         outline=self._volume_color(t), width=5)

        # 刻度
        for deg in range(0, 181, 15):
            rad = math.radians(deg)
            major = deg % 30 == 0
            r1 = r - 8 if major else r - 11
            r2 = r - 16
            x1 = cx + r1 * math.cos(rad)
            y1 = cy - r1 * math.sin(rad)
            x2 = cx + r2 * math.cos(rad)
            y2 = cy - r2 * math.sin(rad)
            c.create_line(x1, y1, x2, y2, fill=self.MUTED if major else "#55555f",
                          width=2 if major else 1)

        # 指针：0 -> 左(180°)，100 -> 右(0°)
        theta = math.radians(180 - value * 1.8)
        px = cx + (r - 22) * math.cos(theta)
        py = cy - (r - 22) * math.sin(theta)
        c.create_line(cx, cy, px, py, fill="#ffffff", width=4, capstyle=tk.ROUND)
        c.create_oval(cx - 7, cy - 7, cx + 7, cy + 7,
                      fill="#ffffff", outline=self.ACCENT, width=2)

        c.create_text(cx, cy + 44, text=f"{value}%", fill=self.TEXT,
                      font=("Segoe UI", 18, "bold"))

    def _show_volume(self, value: int) -> None:
        self.volume_value = max(0, min(100, int(value)))
        self._draw_volume(self.volume_value)
        self._fade_window(self.volume_win, show=True, hide_after=config.OSD_HIDE_DELAY_MS,
                          job_attr="_volume_hide_job")

    # ======================= 消息侧边栏 =======================
    def _create_sidebar_window(self) -> None:
        w, h = 340, 440
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.sidebar_win = self._base_window(w, h, sw - w - 12, int((sh - h) / 2))
        self.sidebar_canvas = tk.Canvas(self.sidebar_win, width=w, height=h,
                                        bg=self.BG, highlightthickness=0)
        self.sidebar_canvas.pack(fill="both", expand=True)
        self._round_rect(self.sidebar_canvas, 2, 2, w - 2, h - 2, 16,
                         fill=self.CARD, outline=self.CARD_BORDER, width=1)
        self.sidebar_frame = tk.Frame(self.sidebar_canvas, bg=self.CARD)
        self.sidebar_canvas.create_window(10, 10, anchor="nw", window=self.sidebar_frame,
                                          width=w - 20, height=h - 20)
        self._render_sidebar()
        self._make_draggable(self.sidebar_win)

    def _render_sidebar(self) -> None:
        for widget in self.sidebar_items:
            widget.destroy()
        self.sidebar_items.clear()

        header = tk.Label(self.sidebar_frame, text=f"未读消息 ({len(self.messages)})",
                          bg=self.CARD, fg=self.TEXT, font=("Segoe UI", 14, "bold"),
                          anchor="w")
        header.pack(fill="x", pady=(0, 10))
        self.sidebar_items.append(header)

        if not self.messages:
            empty = tk.Label(self.sidebar_frame, text="暂无未读消息", bg=self.CARD,
                             fg=self.MUTED, font=("Segoe UI", 12), pady=24)
            empty.pack(anchor="w")
            self.sidebar_items.append(empty)
        else:
            for i, m in enumerate(self.messages):
                selected = i == self.selected_index
                row_bg = "#23232f" if selected else "#1b1b26"
                row = tk.Frame(self.sidebar_frame, bg=row_bg,
                               highlightthickness=1,
                               highlightbackground=self.ACCENT if selected else self.CARD)
                row.pack(fill="x", pady=4)

                src = m.get("src", "?")
                color = self.SRC_COLORS.get(src, "#9aa0a6")
                src_label = tk.Label(row, text=src, bg=row_bg, fg=color,
                                     font=("Segoe UI", 9, "bold"), width=7, anchor="w")
                src_label.pack(side="left", padx=(8, 4), pady=8)

                body = tk.Frame(row, bg=row_bg)
                body.pack(side="left", fill="x", expand=True, pady=6)
                title = tk.Label(body, text=m.get("title", ""), bg=row_bg, fg=self.TEXT,
                                 font=("Segoe UI", 10), anchor="w", justify="left",
                                 wraplength=250)
                title.pack(fill="x")
                t = tk.Label(body, text=m.get("time", ""), bg=row_bg, fg=self.MUTED,
                             font=("Segoe UI", 8), anchor="w")
                t.pack(fill="x")
                self.sidebar_items.append(row)

        clear_btn = tk.Button(self.sidebar_frame, text="清空", command=self._on_clear_click,
                              bg="#262633", fg="#ffffff", activebackground="#333344",
                              activeforeground="#ffffff", relief="flat",
                              font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                              cursor="hand2")
        clear_btn.pack(anchor="e", pady=(12, 0))
        self.sidebar_items.append(clear_btn)

    def _show_sidebar(self) -> None:
        self._render_sidebar()
        hide_after = 0 if self.messages else config.OSD_HIDE_DELAY_MS
        self._fade_window(self.sidebar_win, show=True, hide_after=hide_after,
                          job_attr="_sidebar_hide_job")

    def _on_clear_click(self) -> None:
        self._clear_messages()
        if hasattr(self, "on_clear_requested") and self.on_clear_requested:
            self.on_clear_requested()

    def _add_message(self, src: str, title: str, time_str: str, mid: int = 0) -> None:
        self.messages.append({"src": src, "title": title, "time": time_str, "id": mid})
        # 与 Arduino 端 MAX_MSGS 对齐：只保留最近 N 条，旋钮索引才能一一对应
        if len(self.messages) > config.OSD_MAX_MESSAGES:
            self.messages.pop(0)
        if self.selected_index >= len(self.messages):
            self.selected_index = len(self.messages) - 1
        if self.selected_index < 0:
            self.selected_index = 0
        self._show_sidebar()
        self._update_status()

    def _remove_selected(self) -> None:
        if 0 <= self.selected_index < len(self.messages):
            self.messages.pop(self.selected_index)
        if self.selected_index >= len(self.messages):
            self.selected_index = len(self.messages) - 1
        if self.selected_index < 0:
            self.selected_index = 0
        self._show_sidebar()
        self._update_status()

    def _remove_by_id(self, mid: int) -> None:
        try:
            target = int(mid)
        except (TypeError, ValueError):
            return
        self.messages = [m for m in self.messages if int(m.get("id", -1)) != target]
        if self.selected_index >= len(self.messages):
            self.selected_index = len(self.messages) - 1
        if self.selected_index < 0:
            self.selected_index = 0
        self._show_sidebar()
        self._update_status()

    def _clear_messages(self) -> None:
        self.messages.clear()
        self.selected_index = 0
        self._show_sidebar()
        self._update_status()

    def _set_selected(self, index: int) -> None:
        if not self.messages:
            self.selected_index = 0
        else:
            self.selected_index = max(0, min(int(index), len(self.messages) - 1))
        self._render_sidebar()
        self._show_sidebar()

    # ======================= 状态指示器 =======================
    def _create_status_window(self) -> None:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = 300, 46
        self.status_win = self._base_window(w, h, sw - w - 20, sh - h - 20)
        self.status_canvas = tk.Canvas(self.status_win, width=w, height=h,
                                       bg=self.BG, highlightthickness=0)
        self.status_canvas.pack(fill="both", expand=True)
        self._update_status()
        self.status_win.deiconify()
        self._make_draggable(self.status_win)

    def _update_status(self) -> None:
        c = self.status_canvas
        if not c:
            return
        c.delete("all")
        w, h = 300, 46
        self._round_rect(c, 2, 2, w - 2, h - 2, 23,
                         fill=self.CARD, outline=self.CARD_BORDER, width=1)
        mode_icon = "🎛" if self.current_mode == "control" else "📩"
        mode_text = "控制" if self.current_mode == "control" else "消息"
        dnd_text = "  ·  免打扰" if self.dnd else ""
        text = f"{mode_icon}  {mode_text}   ·   未读 {len(self.messages)}{dnd_text}"
        c.create_text(18, h // 2, text=text, fill=self.TEXT,
                      font=("Segoe UI", 11, "bold"), anchor="w")

    def _set_mode(self, mode: str) -> None:
        self.current_mode = mode
        self._update_status()

    def _set_dnd(self, enabled: bool) -> None:
        self.dnd = enabled
        self._update_status()

    # ======================= 桌面切换动画 =======================
    def _create_desktop_window(self) -> None:
        w, h = 300, 130
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.desktop_win = self._base_window(w, h, int((sw - w) / 2), int((sh - h) / 2))
        self.desktop_canvas = tk.Canvas(self.desktop_win, width=w, height=h,
                                        bg=self.BG, highlightthickness=0)
        self.desktop_canvas.pack(fill="both", expand=True)

    def _show_desktop_animation(self, direction: str) -> None:
        c = self.desktop_canvas
        c.delete("all")
        w, h = 300, 130
        self._round_rect(c, 2, 2, w - 2, h - 2, 18,
                         fill=self.CARD, outline=self.CARD_BORDER, width=1)
        arrow = "◀" if direction == "left" else "▶"
        color = "#7ec8ff" if direction == "left" else "#8fdc8f"
        c.create_text(w // 2, h // 2 - 8, text=arrow, fill=color,
                      font=("Segoe UI", 42, "bold"))
        c.create_text(w // 2, h - 22, text="切换桌面", fill=self.MUTED,
                      font=("Segoe UI", 10))
        self._fade_window(self.desktop_win, show=True, hide_after=1000,
                          job_attr="_desktop_hide_job")

    # ======================= 全屏闪白 =======================
    def _flash_screen(self) -> None:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        flash = tk.Toplevel(self.root)
        flash.overrideredirect(True)
        flash.attributes("-topmost", True)
        flash.attributes("-alpha", 0.35)
        flash.geometry(f"{sw}x{sh}+0+0")
        flash.configure(bg="white")
        flash.after(180, flash.destroy)

    # ======================= 通知 =======================
    def _show_notification(self, title: str, message: str) -> None:
        self._notify_system(title, message)

    def _notify_system(self, title: str, message: str) -> None:
        try:
            from plyer import notification
            notification.notify(title=title, message=message, timeout=4)
            return
        except Exception:
            pass
        try:
            import subprocess
            if __import__("platform").system().lower() == "darwin":
                subprocess.run(["osascript", "-e",
                                f'display notification "{message}" with title "{title}"'],
                               check=False)
                return
        except Exception:
            pass
        try:
            w, h = 340, 96
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            win = self._base_window(w, h, sw - w - 24, 24)
            cv = tk.Canvas(win, width=w, height=h, bg=self.BG, highlightthickness=0)
            cv.pack(fill="both", expand=True)
            self._round_rect(cv, 2, 2, w - 2, h - 2, 14,
                             fill=self.CARD, outline=self.CARD_BORDER, width=1)
            cv.create_text(14, 26, text=title, fill=self.TEXT, anchor="w",
                           font=("Segoe UI", 11, "bold"))
            cv.create_text(14, 54, text=message, fill=self.MUTED, anchor="w",
                           font=("Segoe UI", 10), width=w - 28)
            win.deiconify()
            win.after(4000, win.destroy)
        except Exception:
            pass

    # ======================= 淡入淡出 =======================
    def _fade_window(self, win: tk.Toplevel, show: bool, hide_after: int = 0,
                     job_attr: str = "") -> None:
        if not win:
            return
        if job_attr:
            old_job = getattr(self, job_attr, None)
            if old_job:
                try:
                    self.root.after_cancel(old_job)
                except Exception:
                    pass
        win.deiconify()
        win.lift()
        self._fade_to(win, config.OSD_ALPHA if show else 0.0,
                      hide_after=hide_after, job_attr=job_attr)

    def _fade_to(self, win: tk.Toplevel, target: float, step: float = 0.08,
                 hide_after: int = 0, job_attr: str = "") -> None:
        try:
            current = float(win.attributes("-alpha"))
        except Exception:
            current = 0.0
        if abs(current - target) <= step:
            win.attributes("-alpha", target)
            if target <= 0.0:
                win.withdraw()
            elif hide_after > 0:
                job = self.root.after(hide_after,
                                      lambda: self._fade_to(win, 0.0, job_attr=job_attr))
                if job_attr:
                    setattr(self, job_attr, job)
            return
        nxt = current + (step if target > current else -step)
        win.attributes("-alpha", nxt)
        self.root.after(config.OSD_FADE_MS,
                        lambda: self._fade_to(win, target, step, hide_after, job_attr))
