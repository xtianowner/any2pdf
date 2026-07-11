# purpose: 桌面拖拽小窗 —— pywebview 包住本地 FastAPI 服务,复用同一套 Web 界面
# 创建时间: 2026-06-29 15:13:00
# 更新时间: 2026-06-29 15:13:00
# 时区: Asia/Shanghai
"""双击/运行即开一个原生窗口,把文件拖进去转 PDF。

内部启动一个仅监听 127.0.0.1、随机空闲端口的 FastAPI 服务,再用系统 WebView 加载它,
所以桌面版和 Web 版是同一套界面、同一个转换内核,零重复 UI 代码。
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> int:
    import uvicorn
    import webview

    from server.app import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    if not _wait_ready(port):
        print("本地服务启动失败", file=sys.stderr)
        return 1

    webview.create_window(
        "一键转 PDF", f"http://127.0.0.1:{port}/",
        width=620, height=760, min_size=(480, 600),
    )
    webview.start()  # 阻塞直到窗口关闭
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
