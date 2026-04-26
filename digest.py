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
    """Build a prompt for high-quality WeChat Official Account style summary (Unified)"""
    prompt = """你是一位顶尖的科技自媒体主编，擅长撰写深度、客观且极具吸引力的“公众号式”推文简报。
请根据以下 X (Twitter) 上的博主动态，创作一篇内容精良、排版美观且富有干货的推文综述。

**写作格式要求：**
1. **标题：** 拟定一个吸引人且概括性强的标题，反映本时段最核心的技术动态。
2. **前言：** 简要概述过去几小时关注圈的热议话题或核心基调。
3. **👤 博主深度速递：**
   - **请按博主分别进行详细总结**（针对推文内容质量高的博主进行深度挖掘）。
   - 每个博主的总结包含以下三部分：
     - **主要内容：** 详细总结该博主最新帖子的核心叙事或事件。
     - **核心观点：** 提炼博主表达出的具体洞察、态度或预测。
     - **实用工具/资源：** 如果帖子中提到了任何 AI 工具、开源项目、论文或链接，请务必列出。
     - **来源链接：** 在段落末尾列出推文链接，格式为 [推文1](url), [推文2](url)...
4. **🔥 综合启发：** 结合上述所有博主的动态，总结出 2-3 条对开发者或 AI 使用者的具体启发或行动建议。

**排版建议：**
- 使用 Markdown 语法。
- 使用适当的 Emoji 增加趣味性。
- 层级分明，使用二级标题 (##) 和三级标题 (###)。

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
                "content": "你是一个专业的自媒体主编，擅长撰写极具吸引力且专业度高的公众号文章稿件。输出使用标准 Markdown 格式。"
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
            f.write("---\n")
            f.write(f"date: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("type: X-Daily-Digest\n")
            f.write("tags: [X, AI, Summary]\n")
            f.write("---\n\n")
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
    webhook_url = os.getenv("FEISHU_WEBHOOK")

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
