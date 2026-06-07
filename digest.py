import os
import json
import requests
from datetime import datetime, timedelta
from openai import OpenAI

# --- Configuration ---
DAILY_TWEETS_FILE = "daily_tweets.json"
OBSIDIAN_SYNC_DIR = "obsidian_sync"

def load_daily_tweets():
    """Load accumulated tweets from the daily tweets file"""
    if os.path.exists(DAILY_TWEETS_FILE):
        with open(DAILY_TWEETS_FILE, 'r') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def clear_daily_tweets():
    """Clear the daily tweets file after digest is sent"""
    with open(DAILY_TWEETS_FILE, 'w') as f:
        json.dump([], f)

def group_tweets_by_blogger(tweets):
    """Group tweets by blogger nickname"""
    groups = {}
    for tweet in tweets:
        key = tweet['nickname']
        if key not in groups:
            groups[key] = {
                "username": tweet['username'],
                "nickname": tweet['nickname'],
                "tweets": []
            }
        groups[key]['tweets'].append(tweet)
    return groups

def build_unified_prompt(groups):
    """Build a prompt for an action-focused digest grouped by blogger."""
    prompt = """你是一位优秀的科技记者。

请按博主分组总结本时间段内的 X 推文。

## 要求

1. 不要逐条总结推文。
2. 将同一主题的多条推文融合成一篇短文。
3. 用讲故事和行业观察的方式描述这个博主最近在关注什么、有哪些重要观点、提到了哪些值得关注的工具。
4. 不要使用项目符号。
5. 不要拆分为“观点”“工具”等小节。
6. 每位博主输出一篇 150-300 字的短文。
7. 重点说明：
   - 最近在研究什么
   - 有哪些新发现
   - 为什么值得关注
   - 对行业意味着什么

## 🚫 禁用句式

为了保持行文干练，**严禁**使用以下表达，请直接陈述事实和观点：
- “值得关注的是” / “值得一提的是”
- “可以看出” / “不难发现”
- “总体来看”
- “从某种意义上说”

## 输出格式

每个博主依次输出如下结构：

### @[博主中文名字]

（150-300字文章）

### 原文链接

- [推文标题/核心内容1](链接1)
- [推文标题/核心内容2](链接2)
...

## 链接要求

凡是文章中提到的观点、案例、工具，必须在文末提供对应原文链接。
必须保留所有被引用推文的原文链接。
不允许出现无法追溯来源的信息。
如果文章中的观点来自某条推文，则对应链接必须出现在“原文链接”部分。

## 去重要求

当同一主题在多条推文中重复出现时，将其融合为一个观点进行讲述，不要重复描述。
避免流水账。
避免简单复述推文。
避免同义反复。

## 最终输出

最后增加：

### 本期趋势

用 200 字以内总结本时间段最值得关注的行业趋势、新工具和重要变化。
不要重复前文内容。
不要统计词频。
重点解释为什么值得关注。

以下是推文原始数据：

"""
    for nick, group in groups.items():
        prompt += f"\n--- {nick} (@{group['username']}) ---\n"
        for i, t in enumerate(group['tweets'], 1):
            rt_tag = "(转帖) " if t.get('is_retweet') else ""
            prompt += f"\n[推文{i} - {t['time']}] {rt_tag}{t['text']}\n链接: {t['url']}"
            if t.get('quoted_tweet'):
                qt = t['quoted_tweet']
                prompt += f"\n  └─ 引用自 @{qt['username']}: {qt['text']}"
            prompt += "\n"

    return prompt

def generate_summary(prompt, api_key):
    """Call DeepSeek API to generate summary"""
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {
                "role": "system",
                "content": "你是一位优秀的科技记者。输出标准 Markdown，按博主分组以讲故事和行业观察的方式写作总结短文（每位博主150-300字），严禁使用“值得关注的是”、“可以看出”等套话，直接陈述事实与观点，并附带原文链接与本期趋势。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.6,
        max_tokens=3000
    )

    return response.choices[0].message.content

def save_to_obsidian_sync(content):
    """Save the content for local Obsidian sync"""
    if not os.path.exists(OBSIDIAN_SYNC_DIR):
        os.makedirs(OBSIDIAN_SYNC_DIR, exist_ok=True)

    now = datetime.utcnow() + timedelta(hours=8)
    filename = f"{now.strftime('%Y-%m-%d %H%M')} X简报.md"
    file_path = os.path.join(OBSIDIAN_SYNC_DIR, filename)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Saved to local Obsidian sync folder: {file_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to save for Obsidian: {e}")
        return False

def build_feishu_card(summary, date_str):
    """Build a Feishu card using the unified WeChat-style summary"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📝 X 帖子动态综述 — {date_str}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": summary
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "⏰ 此摘要已同步至 Obsidian\n🤖 Powered by DeepSeek"
                    }
                }
            ]
        }
    }

def main():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    # Prefer FEISHU_WEBHOOK_DIGEST for summaries to avoid getting drowned out by individual tweets
    webhook_url = os.getenv("FEISHU_WEBHOOK_DIGEST") or os.getenv("FEISHU_WEBHOOK")

    if not api_key:
        print("Error: Missing DEEPSEEK_API_KEY.")
        return

    # Load tweets
    tweets = load_daily_tweets()
    if not tweets:
        print("No new tweets to summarize.")
        return

    # Date info (Beijing time)
    now = datetime.utcnow() + timedelta(hours=8)
    date_str = now.strftime('%Y-%m-%d %H:%M')

    print(f"Generating unified summary for {len(tweets)} tweets...")
    
    groups = group_tweets_by_blogger(tweets)
    prompt = build_unified_prompt(groups)
    summary = generate_summary(prompt, api_key)

    # 1. Save for Obsidian (local repo folder)
    save_to_obsidian_sync(summary)

    # 2. Push to Feishu
    if webhook_url:
        payload = build_feishu_card(summary, date_str)
        response = requests.post(webhook_url, json=payload)
        print(f"Digest pushed to Feishu. Status: {response.status_code}")
    else:
        print("Warning: FEISHU_WEBHOOK not set, skipping Feishu push.")

    # 3. Clear daily tweets
    clear_daily_tweets()
    print("Daily tweets cleared.")

if __name__ == "__main__":
    main()
