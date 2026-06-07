#!/bin/bash
set -o pipefail
export LC_ALL=C

# sync_to_obsidian.sh
# 功能：从 GitHub posts 分支拉取最新的 X 帖子要点总结，同步到本地 Obsidian iCloud 目录
# 路径：/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work/X推送

REMOTE_URL="https://github.com/sourit2001/X2feishu.git"
RUNTIME_DIR="/Users/lizhu/Library/Application Support/X2feishu"
CACHE_REPO="$RUNTIME_DIR/posts.git"
OBSIDIAN_DIR="/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work/X推送"
LOG_DIR="/Users/lizhu/Library/Logs/X2feishu"
LOG_FILE="$LOG_DIR/sync_obsidian.log"
TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/x2feishu-posts.XXXXXX")

trap 'rm -rf "$TEMP_DIR"' EXIT

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"
echo "[$( date '+%Y-%m-%d %H:%M:%S' )] 开始同步 X 帖子公众号格式总结..." | tee -a "$LOG_FILE"

# 1. 获取 GitHub Actions 发布到 posts 分支的简报，缓存位于 Library 以支持后台执行
if [ ! -d "$CACHE_REPO" ]; then
    if ! git init --bare "$CACHE_REPO" 2>&1 | tee -a "$LOG_FILE"; then
        echo "  初始化 Git 缓存失败，已终止同步" | tee -a "$LOG_FILE"
        exit 1
    fi
fi
if ! git --git-dir="$CACHE_REPO" fetch --force "$REMOTE_URL" posts:refs/remotes/origin/posts 2>&1 | tee -a "$LOG_FILE"; then
    echo "  拉取 posts 分支失败，已终止同步" | tee -a "$LOG_FILE"
    exit 1
fi
if ! git --git-dir="$CACHE_REPO" archive --format=tar refs/remotes/origin/posts -- '*.md' | tar -xf - -C "$TEMP_DIR"; then
    echo "  提取 posts 分支简报失败，已终止同步" | tee -a "$LOG_FILE"
    exit 1
fi

# 2. 确保 Obsidian 目标目录存在
mkdir -p "$OBSIDIAN_DIR"

# 3. 同步 posts 分支下的 .md 文件
COPIED=0
# 检查是否有文件
if [ -d "$TEMP_DIR" ]; then
    for file in "$TEMP_DIR"/*.md; do
        [ -f "$file" ] || continue
        filename=$(basename "$file")
        dest="$OBSIDIAN_DIR/$filename"
        # 只复制不存在的文件（文件名包含时间戳，通常不会重复）
        if [ ! -f "$dest" ]; then
            if cp "$file" "$dest"; then
                echo "  ✅ 已同步: $filename" | tee -a "$LOG_FILE"
                COPIED=$((COPIED + 1))
            else
                echo "  复制失败: $filename" | tee -a "$LOG_FILE"
                exit 1
            fi
        fi
    done
fi

if [ "$COPIED" -eq 0 ]; then
    echo "  ℹ️  没有新的总结报告需要同步" | tee -a "$LOG_FILE"
else
    echo "  🎉 共同步了 $COPIED 份总结报告" | tee -a "$LOG_FILE"
fi

echo "[$( date '+%Y-%m-%d %H:%M:%S' )] 同步完成" | tee -a "$LOG_FILE"
