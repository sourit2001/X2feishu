import os
import json
import requests
from datetime import datetime, timedelta
# Mocking the heavy parts
def mock_generate_summary(prompt, api_key):
    return """# 🚀 模拟测试：AI 圈的暗流涌动

## 1. 深度洞察
这是模拟生成的公众号风格内容。AI 领域今天发生了一些大事。 [🔗 查看原推](https://twitter.com/test)

## 2. 博主动态
- **马斯克**: 正在测试星舰。 [推文1](https://twitter.com/elonmusk/1)
- **奥特曼**: OpenAI 发布了新模型。 [推文1](https://twitter.com/sama/1)
"""

# Import the logic from digest.py but replace generate_summary
import digest
digest.generate_summary = mock_generate_summary

def test_run():
    print("开始模拟运行测试...")
    
    # Create dummy data if needed
    test_tweets = [
        {"nickname": "马斯克", "username": "elonmusk", "text": "Testing Starship", "url": "https://twitter.com/elonmusk/1", "time": "2026-04-19 12:00", "is_retweet": False},
        {"nickname": "奥特曼", "username": "sama", "text": "New model out now", "url": "https://twitter.com/sama/1", "time": "2026-04-19 12:05", "is_retweet": False}
    ]
    
    with open("daily_tweets_test.json", "w") as f:
        json.dump(test_tweets, f)
    
    # Override the file path for test
    digest.DAILY_TWEETS_FILE = "daily_tweets_test.json"
    
    # Mocking environment
    os.environ["DEEPSEEK_API_KEY"] = "mock_key"
    os.environ["FEISHU_WEBHOOK"] = "" # Don't actually push to Feishu during test
    
    # Run main logic
    print("正在调用生成与同步逻辑...")
    digest.main()
    
    # Check if file was created in obsidian_sync
    files = os.listdir("obsidian_sync")
    print(f"检测到生成的报告文件: {files}")
    
    if any("X简报.md" in f for f in files):
        print("✅ 测试成功：已成功生成 Obsidian Markdown 报告并保存。")
        # Cleanup
        os.remove("daily_tweets_test.json")
    else:
        print("❌ 测试失败：未检测到生成的报告。")

if __name__ == "__main__":
    test_run()
