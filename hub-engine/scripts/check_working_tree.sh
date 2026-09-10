#!/usr/bin/env bash
# @version V1.0 / 2026-09-10 / Hermes / hub-engine working tree 守护扫描脚本
#
# 作用：扫 git working tree，modified/staged/untracked 超阈值则报警
# 触发原因：trae work ruff format 48 文件 2 天未 commit 未报警（2026-09-10 实证）
# 调用：
#   bash scripts/check_working_tree.sh                    # 扫描当前仓
#   bash scripts/check_working_tree.sh --threshold 5      # 自定义阈值
#   bash scripts/check_working_tree.sh --auto-stash        # 自动 stash（风险高，需用户确认）
# 输出：
#   JSON 报告到 stdout
#   exit 0 = 正常
#   exit 1 = 异常（超阈值，需要人工处置）

set -e

# 默认阈值：3（按 dual-platform-coherence-discipline §4 标准）
THRESHOLD=3
AUTO_STASH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --threshold)
            THRESHOLD="$2"
            shift 2
            ;;
        --auto-stash)
            AUTO_STASH=true
            shift
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

# 扫描 working tree
MODIFIED=$(git status --short | wc -l)
MODIFIED_FILES=$(git status --short | awk '{print $2}' | tr '\n' ',' | sed 's/,$//')

# 按 mtime 分类（找集中 vs 分散）
if [ "$MODIFIED" -gt 0 ]; then
    MTIME_DISTINCT=$(git status --short | awk '{print $2}' | xargs -I{} stat -c "%y" {} 2>/dev/null | cut -d. -f1 | sort -u | wc -l)
else
    MTIME_DISTINCT=0
fi

# 判定
if [ "$MODIFIED" -ge "$THRESHOLD" ]; then
    STATUS="ALARM"
    RECOMMENDATION="必须分析来源，commit / stash / reset 三选一"
    EXIT_CODE=1
else
    STATUS="OK"
    RECOMMENDATION="working tree 干净"
    EXIT_CODE=0
fi

# 输出 JSON 报告
cat <<EOF
{
  "status": "$STATUS",
  "modified_count": $MODIFIED,
  "threshold": $THRESHOLD,
  "mtime_distinct_count": $MTIME_DISTINCT,
  "modified_files": "$MODIFIED_FILES",
  "recommendation": "$RECOMMENDATION",
  "auto_stash_enabled": $AUTO_STASH,
  "scan_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

exit $EXIT_CODE