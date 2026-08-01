import os
import json
import tempfile
from unittest.mock import patch
# Mocking the heavy parts
def mock_generate_summary(prompt, api_key):
    return """# 🚀 模拟测试：AI 圈的暗流涌动

## 1. 深度洞察
这是模拟生成的公众号风格内容。AI 领域今天发生了一些大事。 [🔗 查看原推](https://twitter.com/test)

## 2. 博主动态
- **马斯克**: 正在测试星舰。 [推文1](https://twitter.com/elonmusk/1)
- **奥特曼**: OpenAI 发布了新模型。 [推文1](https://twitter.com/sama/1)
"""

def mock_send_to_feishu(webhook_url, payload):
    return {"code": 0}

import digest

def test_run():
    print("开始模拟运行测试...")
    
    # Create dummy data if needed
    test_tweets = [
        {"nickname": "马斯克", "username": "elonmusk", "text": "Testing Starship", "url": "https://twitter.com/elonmusk/1", "time": "2026-04-19 12:00", "is_retweet": False},
        {"nickname": "奥特曼", "username": "sama", "text": "New model out now", "url": "https://twitter.com/sama/1", "time": "2026-04-19 12:05", "is_retweet": False}
    ]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        digest.DAILY_TWEETS_FILE = os.path.join(temp_dir, "daily_tweets.json")
        digest.OBSIDIAN_SYNC_DIR = os.path.join(temp_dir, "obsidian_sync")

        with open(digest.DAILY_TWEETS_FILE, "w") as f:
            json.dump(test_tweets, f)

        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "mock_key",
                "FEISHU_WEBHOOK": "https://example.invalid/mock",
            },
            clear=False,
        ), patch.object(
            digest, "generate_summary", mock_generate_summary
        ), patch.object(
            digest, "send_to_feishu", mock_send_to_feishu
        ):
            print("正在调用生成与同步逻辑...")
            digest.main()

        files = os.listdir(digest.OBSIDIAN_SYNC_DIR)
        print(f"检测到生成的报告文件: {files}")

        if any("X简报.md" in f for f in files):
            print("✅ 测试成功：已成功生成 Obsidian Markdown 报告并保存。")
        else:
            raise AssertionError("未检测到生成的报告。")

if __name__ == "__main__":
    test_run()
