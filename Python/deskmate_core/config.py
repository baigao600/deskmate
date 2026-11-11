"""
DeskMate Pro - 配置模块（deskmate_core）

这里集中管理串口、IMAP 邮箱、界面等可配置项。
打包成 exe/app 后，这些值会固定在程序中；
如需运行时可修改，可以进一步改为读取同目录下的 config.json。
"""

import os

# ======================= 串口配置 =======================
# 若设为 None，程序会自动选择第一个可用串口；
# 若你的电脑上有多个串口，请直接填写端口名，例如：
#   Windows: "COM3"
#   macOS:   "/dev/cu.usbmodem14101"
#   Linux:   "/dev/ttyUSB0"
SERIAL_PORT = None
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 1.0            # 秒
SERIAL_RECONNECT_INTERVAL = 3.0  # 断开后重连间隔（秒）

# 自测开关：启动后自动向 Arduino 发送 selftest 指令，
# 用于验证敲击截屏和倾斜切换桌面。验证完成后请改为 False。
SELF_TEST_ON_START = True

# ======================= IMAP 邮箱配置 =======================
# 请填写你的邮箱信息。IMAP 服务器/用户名/密码可配置。
# 常见服务器示例：
#   Gmail:       imap.gmail.com, 端口 993, SSL=True
#   Outlook:     outlook.office365.com, 端口 993, SSL=True
#   QQ 邮箱:     imap.qq.com, 端口 993, SSL=True
IMAP_ENABLED = False          # 设为 True 并填写下方账号密码后才启用邮件提醒
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
IMAP_USE_SSL = True
IMAP_USER = "your_email@example.com"
IMAP_PASSWORD = "your_app_password"   # Gmail 请使用应用专用密码
IMAP_CHECK_INTERVAL = 60              # 秒

# ======================= 日历配置（预留） =======================
# 本版本暂未实现日历同步，仅保留配置占位。
# 扩展思路：
#   1. 使用 Google Calendar API 或 CalDAV 库（如 caldav）查询未来 24 小时日程；
#   2. 在 NotificationListener 中新增一个后台线程，按 CALENDAR_CHECK_INTERVAL 轮询；
#   3. 检测到新日程时调用 self.on_new_message({"src": "calendar", ...})。
CALENDAR_CHECK_INTERVAL = 300

# ======================= 微信消息配置 =======================
# 可选本地集成。仓库发行版不包含此模块，缺少模块时自动跳过。
WECHAT_ENABLED = True
WECHAT_POLL_INTERVAL = 2          # 轮询新消息间隔（秒）
WECHAT_LISTEN_CHATS = []          # 只监听指定会话名；留空表示监听所有会话
WECHAT_MAX_TITLE_LEN = 32         # 标题截断长度（Arduino 内存有限，取较短预览）
WECHAT_PRELOAD_UNREAD = True      # 启动时预载微信已有未读消息，便于旋钮立即浏览
WECHAT_PRELOAD_LIMIT = 4          # 预载未读消息总数上限（与 Arduino 端 MAX_MSGS 一致）
WECHAT_PRELOAD_PER_SESSION = 5    # 每个会话最多预载的未读条数

# OSD 侧边栏最多保留的未读消息条数（与 Arduino 端 MAX_MSGS 保持一致）
OSD_MAX_MESSAGES = 4

# ======================= 截图保存目录 =======================
# None 表示保存到用户桌面
SCREENSHOT_DIR = None

# ======================= 界面配置 =======================
OSD_ALPHA = 0.85            # OSD 默认不透明度
OSD_FADE_MS = 12            # 淡入/淡出每次步进间隔
OSD_HIDE_DELAY_MS = 1800    # 音量/动画窗口显示后自动隐藏的延时


def screenshot_dir() -> str:
    """返回截图保存目录，默认使用用户桌面。"""
    if SCREENSHOT_DIR:
        path = SCREENSHOT_DIR
    else:
        path = os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(path, exist_ok=True)
    return path
