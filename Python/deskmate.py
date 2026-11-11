"""
DeskMate Pro - 电脑端启动脚本

直接运行： python deskmate.py
打包入口也指向此文件。
"""

import os
import sys
import tempfile
import time
import traceback

# PyInstaller --windowed 模式下 sys.stdout / sys.stderr 可能为 None，
# 提前替换为 devnull，避免 print 语句抛出 AttributeError。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _log_crash() -> None:
    """把未捕获异常写入崩溃日志，便于打包后（无控制台）排查问题。"""
    try:
        path = os.path.join(tempfile.gettempdir(), "DeskMatePro_crash.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            traceback.print_exc(file=f)
    except Exception:
        pass


def _main() -> None:
    from deskmate_core.main import run

    run()


if __name__ == "__main__":
    try:
        _main()
    except Exception:
        _log_crash()
        raise
