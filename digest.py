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
    prompt = """你是一位专业的科技信息分析编辑。
请根据以下 X (Twitter) 上的博主动态，输出一篇简洁、可执行的中文简报。

**写作格式要求：**
1. 不要写文章标题。
2. 不要写前言、导语、开场白或总体概述。
3. 不要输出 YAML、表格、笔记属性、日期、type、tags 等元信息。
4. 正文直接按博主分组输出，每个博主只写中文名字，不要写 X 账号、用户名或括号。
5. 每个博主下面只保留两类内容：
   - **要点：** 用 1-3 条 bullet 总结值得关注的信息，避免复述无关细节。
   - **可以行动：** 用 1-3 条 bullet 写用户可以采取的行动、验证方式、进一步研究方向或值得跟进的问题。
6. 不要单独写“实用工具/资源”“来源链接”“综合启发”等章节。
7. 如需保留来源，只在对应 bullet 末尾放一个简短链接，例如 [原文](url)。
8. 如果某个博主内容价值不高或没有可行动信息，可以跳过。

**排版建议：**
- 使用 Markdown 语法。
- 每个博主使用二级标题，例如 `## 宝玉`。
- 标题下面只使用 `**要点：**` 和 `**可以行动：**` 两个小段。
- 语言要短、直接、信息密度高，减少形容词和公众号腔。

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
                "content": "你是一个专业的科技信息分析编辑。输出标准 Markdown，只保留按博主分组的要点和可行动建议，不写标题、前言或元信息。"
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
