#!/bin/bash
# 疆途·智能巡查管理平台 V1.0 - 启动脚本
# 用法: ./run.sh [模式参数]
#
# 模式参数:
#   (无参数)                 默认主程序（GUI）
#   --jt-mission-webview    航线规划器
#   --jt-map-webview        地图窗口
#   --jt-sanzi-login        三资平台登录
#   --jt-sanzi-workbench    三资工作台
#   --jt-anyang-export      安阳三资在线导出
#   --jt-runtime-self-test  运行时自检

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

source .venv/bin/activate
exec python3.11 main.py "$@"
