#!/usr/bin/env bash
# LM Studio 健康检查脚本
# 用途：系统启动时或定时任务中检测 LM Studio 服务状态
# 功能：检测进程、端口、API、模型加载状态

set -euo pipefail

LMS_EXE="${LOCALAPPDATA}/Programs/LM Studio/resources/app/.webpack/lms.exe"
API_URL="http://127.0.0.1:1234"
REQUIRED_MODELS=("text-embedding-bge-m3" "qwen/qwen3.5-9b" "paddleocr-vl-1.6")

echo "==== LM Studio 健康检查 ===="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 检测 LM Studio 安装
if [ ! -f "$LMS_EXE" ]; then
    echo "✗ LM Studio 未安装"
    echo "  预期位置: $LMS_EXE"
    echo ""
    echo "【修复指引】"
    echo "  1. 下载 LM Studio: https://lmstudio.ai/"
    echo "  2. 安装到默认位置"
    echo "  3. 重新运行此脚本"
    exit 1
fi
echo "✓ LM Studio 已安装"

# 2. 检测服务器状态
echo ""
echo "检查服务器状态..."
if "$LMS_EXE" server status 2>&1 | grep -q "running"; then
    echo "✓ 服务器正在运行"
    "$LMS_EXE" server status
else
    echo "✗ 服务器未运行"
    echo ""
    echo "【修复指引】"
    echo "  自动启动: $(dirname "$0")/start_lm_studio.sh"
    echo "  或手动启动: lms server start --port 1234"
    exit 2
fi

# 3. 检测端口监听
echo ""
echo "检查端口 1234..."
if netstat -an 2>/dev/null | grep -q "127.0.0.1:1234.*LISTENING"; then
    echo "✓ 端口 1234 正在监听"
else
    echo "✗ 端口 1234 未监听"
    exit 3
fi

# 4. 检测 API 可用性
echo ""
echo "检查 API 端点..."
if curl -s --max-time 3 "$API_URL/v1/models" >/dev/null 2>&1; then
    echo "✓ API 端点可访问"
else
    echo "✗ API 端点不可访问"
    echo "  URL: $API_URL/v1/models"
    exit 4
fi

# 5. 检测模型加载状态
echo ""
echo "检查已加载模型..."
LOADED_MODELS=$("$LMS_EXE" ps 2>&1)

if echo "$LOADED_MODELS" | grep -q "No models are currently loaded"; then
    echo "⚠ 警告: 无模型已加载"
    echo ""
    echo "【修复指引】"
    echo "  列出可用模型: lms ls"
    echo "  加载模型: lms load <model-path>"
    echo ""
    echo "  需要的模型:"
    for model in "${REQUIRED_MODELS[@]}"; do
        echo "    - $model"
    done
    exit 5
fi

echo "✓ 已加载模型:"
echo "$LOADED_MODELS" | grep -E "^\s+(text-embedding|qwen|paddleocr)" || echo "  (未找到核心模型)"

# 6. 验证核心模型
echo ""
echo "验证核心模型..."
MISSING_MODELS=()
for model in "${REQUIRED_MODELS[@]}"; do
    if ! "$LMS_EXE" ls 2>&1 | grep -q "$model"; then
        MISSING_MODELS+=("$model")
    fi
done

if [ ${#MISSING_MODELS[@]} -gt 0 ]; then
    echo "⚠ 警告: 以下核心模型未下载:"
    for model in "${MISSING_MODELS[@]}"; do
        echo "  - $model"
    done
    echo ""
    echo "【修复指引】"
    echo "  搜索并下载: lms get <model-name>"
else
    echo "✓ 所有核心模型已就绪"
fi

echo ""
echo "==== 健康检查完成 ===="
exit 0
