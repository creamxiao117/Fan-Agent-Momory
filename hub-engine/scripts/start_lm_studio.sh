#!/usr/bin/env bash
# LM Studio 自动启动脚本
# 用途：通过 CLI 启动 LM Studio 本地服务器，无需手动操作 UI
# 依赖：LM Studio 已安装且模型已下载

set -euo pipefail

LMS_EXE="${LOCALAPPDATA}/Programs/LM Studio/resources/app/.webpack/lms.exe"
DEFAULT_PORT=1234
DEFAULT_BIND="127.0.0.1"

echo "==== LM Studio 服务器启动脚本 ===="

# 检查 lms CLI 是否存在
if [ ! -f "$LMS_EXE" ]; then
    echo "✗ 错误: 未找到 LM Studio CLI 工具"
    echo "  预期位置: $LMS_EXE"
    echo "  请确认 LM Studio 已正确安装"
    exit 1
fi

echo "✓ 找到 LM Studio CLI: $LMS_EXE"

# 检查服务器当前状态
echo ""
echo "检查服务器状态..."
if "$LMS_EXE" server status 2>&1 | grep -q "running"; then
    echo "✓ 服务器已在运行"
    "$LMS_EXE" server status
    exit 0
fi

echo "服务器未运行，正在启动..."

# 启动服务器
echo ""
echo "启动参数:"
echo "  - 端口: ${1:-$DEFAULT_PORT}"
echo "  - 绑定地址: ${2:-$DEFAULT_BIND}"
echo ""

"$LMS_EXE" server start \
    --port "${1:-$DEFAULT_PORT}" \
    --bind "${2:-$DEFAULT_BIND}"

# 验证启动结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✓ 服务器启动成功！"
    echo ""
    "$LMS_EXE" server status
    
    echo ""
    echo "==== 可用命令 ===="
    echo "  查看状态: lms server status"
    echo "  停止服务: lms server stop"
    echo "  加载模型: lms load <model-path>"
    echo "  列出模型: lms ls"
else
    echo "✗ 服务器启动失败"
    exit 1
fi
