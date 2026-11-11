# DeskMate Pro

DeskMate Pro 是一款基于 Arduino 的桌面控制器。电脑端使用 Python 和 Tkinter，固件与电脑通过 USB 串口交换逐行 JSON（115200 波特）。

- **控制模式**：调节音量、控制媒体播放、倾斜切换虚拟桌面、敲击触发截屏。
- **消息模式**：在 OLED 上浏览提醒，配合桌面弹窗使用。支持通过 IMAP 检查新邮件，日历同步为预留功能。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| [Arduino/DeskMatePro](Arduino/DeskMatePro) | 主固件 |
| [Arduino](Arduino) | OLED、I²C 和加速度计诊断草图 |
| [Python](Python) | 桌面应用、依赖清单和 PyInstaller 配置 |
| [外壳模板](enclosure_template.svg) | 外壳设计图，另附 [PNG 预览](enclosure_template.png) |

## Arduino 固件

硬件以 Seeed Studio Grove Beginner Kit for Arduino 为基准。主固件的编译目标是 Arduino Uno（ATmega328P）。

| 模块 | 默认连接 |
| --- | --- |
| 旋钮 | A0 |
| 按钮 | D6 |
| 蜂鸣器 | D3 |
| 单色 LED | D4 |
| OLED | I²C，地址 `0x3C` |
| LIS3DHTR 加速度计 | I²C，尝试 `0x19` 和 `0x18` |

1. 在 Arduino IDE 中安装 Arduino AVR Boards 和 U8g2 库。
2. 打开 [DeskMatePro.ino](Arduino/DeskMatePro/DeskMatePro.ino)，选择 **Arduino Uno** 和对应的串口。
3. 编译并上传，随后可用串口监视器查看输出。启动 Python 应用前请关闭串口监视器。

如果使用 Arduino CLI，在仓库根目录执行：

```sh
arduino-cli compile --fqbn arduino:avr:uno Arduino/DeskMatePro
```

## 桌面应用

建议使用 Windows 和 Python 3.12，确保 Python 安装包含 Tkinter。音量控制使用 Windows 的 pycaw，macOS 有部分功能的回退实现。

在仓库根目录执行：

```sh
cd Python
python -m pip install -r requirements.txt
python deskmate.py
```

- 如果自动选错串口，在 [config.py](Python/deskmate_core/config.py) 中将 `SERIAL_PORT` 指定为实际端口，例如 `COM3`。
- 邮件提醒默认关闭。需要时在本地配置 IMAP 服务器、用户名和应用专用密码，再将 `IMAP_ENABLED` 设为 `True`。请勿提交邮箱凭据。
- 如果希望关闭启动时的固件自测，将 `SELF_TEST_ON_START` 设为 `False`。
- 仓库版提供 IMAP 邮件提醒，微信监听模块仅保留在原本的本地副本中。

## 操作

| 操作 | 控制模式 | 消息模式 |
| --- | --- | --- |
| 转动旋钮 | 调节音量 | 浏览未读提醒 |
| 单击按钮 | 播放或暂停 | 打开当前提醒 |
| 双击按钮 | 下一曲 | 清除未读提醒 |
| 长按按钮 | 切换静音 | 切换免打扰 |
| 三击按钮 | 切到消息模式 | 切回控制模式 |
| 左右倾斜 | 切换虚拟桌面 | — |
| 敲击 | 截屏并保存至桌面 | — |

## Windows 打包

在 `Python/` 目录运行：

```sh
python -m pip install pyinstaller
python -m PyInstaller --clean DeskMatePro.spec
```

生成文件位于 `Python/dist/DeskMatePro.exe`。

## 串口协议示例

```jsonl
{"evt":"volume","val":45}
{"evt":"btn","act":"single"}
{"evt":"tilt","dir":"left"}
{"cmd":"sync_volume","val":50}
{"cmd":"new_msg","src":"email","title":"会议邀请","time":"14:00","id":3}
```

`evt` 由固件发往电脑，`cmd` 由电脑发往固件。每条消息以换行符结束。
