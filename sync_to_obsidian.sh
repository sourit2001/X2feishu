#!/bin/bash
# sync_to_obsidian.sh
# 功能：从 GitHub 拉取最新的 X 帖子要点总结，同步到本地 Obsidian iCloud 目录
# 路径：/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work/X帖子

REPO_DIR="/Users/lizhu/Downloads/CCR/X2飞书/X2feishu"
OBSIDIAN_DIR="/Users/lizhu/Library/Mobile Documents/iCloud~md~obsidian/Documents/my ai work/X帖子"
LOG_FILE="$REPO_DIR/sync_obsidian.log"

echo "[$( date '+%Y-%m-%d %H:%M:%S' )] 开始同步 X 帖子公众号格式总结..." | tee -a "$LOG_FILE"

# 1. 进入仓库目录，拉取最新内容
cd "$REPO_DIR" || exit
git pull --rebase origin main 2>&1 | tee -a "$LOG_FILE"

# 2. 确保 Obsidian 目标目录存在
mkdir -p "$OBSIDIAN_DIR"

# 3. 同步 obsidian_sync/ 下的 .md 文件
COPIED=0
# 检查是否有文件
if [ -d "$REPO_DIR/obsidian_sync" ]; then
    for file in "$REPO_DIR/obsidian_sync"/*.md; do
        [ -f "$file" ] || continue
        filename=$(basename "$file")
        dest="$OBSIDIAN_DIR/$filename"
        # 只复制不存在的文件（文件名包含时间戳，通常不会重复）
        if [ ! -f "$dest" ]; then
            cp "$file" "$dest"
            echo "  ✅ 已同步: $filename" | tee -a "$LOG_FILE"
            COPIED=$((COPIED + 1))
        fi
    done
fi

if [ "$COPIED" -eq 0 ]; then
    echo "  ℹ️  没有新的总结报告需要同步" | tee -a "$LOG_FILE"
else
    echo "  🎉 共同步了 $COPIED 份总结报告" | tee -a "$LOG_FILE"
fi

echo "[$( date '+%Y-%m-%d %H:%M:%S' )] 同步完成" | tee -a "$LOG_FILE"
