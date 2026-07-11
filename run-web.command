#!/bin/bash
# 双击启动「网页版」一键转 PDF。浏览器会自动打开,把文件拖进去即可转。
# 停止:关闭本终端窗口,或在窗口里按 Ctrl+C。
cd "$(dirname "$0")" || exit 1

# 先清掉可能残留的旧服务(避免用到旧代码),确保每次都是最新版
pkill -f "server/app.py" 2>/dev/null
lsof -ti tcp:8765 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

source /opt/miniconda3/etc/profile.d/conda.sh
conda activate any2pdf

echo "============================================"
echo "  一键转 PDF · 网页版"
echo "  地址: http://127.0.0.1:8765"
echo "  停止: 关闭此窗口 或按 Ctrl+C"
echo "============================================"
( sleep 1.5; open "http://127.0.0.1:8765" ) &
python server/app.py
