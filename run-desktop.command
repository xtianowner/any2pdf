#!/bin/bash
# 双击启动「桌面小窗」一键转 PDF。弹出原生窗口,把文件拖进去即可转。
# 停止:关闭那个窗口即可。
# (桌面版每次用全新随机端口、独立进程,自动加载最新代码,不会和网页版冲突。)
cd "$(dirname "$0")" || exit 1
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate any2pdf
echo "正在打开「一键转 PDF」桌面窗口…(关闭窗口即退出)"
python desktop/app.py
