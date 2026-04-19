import os
import json
import requests
from datetime import datetime, timedelta
from openai import OpenAI

# --- Configuration ---
# We save to a local folder in the repo so GitHub Actions can commit it.
# The user's local cron job will then pull and copy it to iCloud.
OBSIDIAN_PATH = "obsidian_sync"
DAILY_TWEETS_FILE = "daily_tweets.json"

def load_daily_tweets():
    """Load accumulated tweets (usually from the last 2 hours if triggered regularly)"""
    if os.path.exists(DAILY_TWEETS_FILE):
        with open(DAILY_TWEETS_FILE, 'r') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def clear_daily_tweets():
    """Clear the daily tweets file after processing"""
    with open(DAILY_TWEETS_FILE, 'w') as f:
        json.dump([], f)

def group_tweets_by_blogger(tweets):
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

def build_wechat_prompt(groups):
    """Build a prompt for high-quality WeChat Official Account style summary"""
    prompt = """你是一位顶尖的科技自媒体主编，擅长撰写深度、客观且极具吸引力的“公众号式”新闻综述。
请根据以下 X (Twitter) 上的博主动态，创作一篇内容精良、排版美观的推文综述。

**写作风格：**
1. **标题：** 请拟定一个极具吸引力、带点“标题党”风味但不过分的深度标题。
2. **前言：** 用 100 字左右概述过去几小时全球 AI 和技术圈发生的重大变化或核心情绪。
3. **今日核心要点（🔥 深度洞察）：** 
   - 提取 3 个最核心的变化或观点。
   - 每一个要点都要有深度分析（为什么重要？可能的影响是什么？）。
   - **务必嵌入来源链接：** 在每个要点结束时，使用 [🔗 查看原推](url) 的格式。
4. **博主动态精选（👤 现场播报）：**
   - 按博主分组，用一段话（30-50字）精彩地点评该博主的最新观点。
   - 在该博主段落末尾，按顺序列出其所有推文链接：[推文1](url), [推文2](url)...
5. **结语：** 简短的点评或一个启发性的问题，引导读者思考。

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

def generate_wechat_summary(prompt, api_key):
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
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

def save_to_obsidian(content):
    """Save the content to Obsidian vault with a timestamped filename"""
    if not os.path.exists(OBSIDIAN_PATH):
        try:
            os.makedirs(OBSIDIAN_PATH, exist_ok=True)
        except Exception as e:
            print(f"Error creating directory: {e}")
            return False

    now = datetime.utcnow() + timedelta(hours=8)
    filename = f"{now.strftime('%Y-%m-%d %H%M')} X简报.md"
    file_path = os.path.join(OBSIDIAN_PATH, filename)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            # Add Frontmatter for better Obsidian organization
            f.write("---\n")
            f.write(f"date: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("type: X-Daily-Digest\n")
            f.write("tags: [X, AI, Summary]\n")
            f.write("---\n\n")
            f.write(content)
        print(f"✅ Successfully saved to Obsidian: {file_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to save to Obsidian: {e}")
        return False

def main():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY not found.")
        return

    tweets = load_daily_tweets()
    if not tweets:
        print("No new tweets to summarize for Obsidian.")
        return

    print(f"Found {len(tweets)} tweets. Generating WeChat style summary...")
    
    groups = group_tweets_by_blogger(tweets)
    prompt = build_wechat_prompt(groups)
    summary = generate_wechat_summary(prompt, api_key)
    
    if save_to_obsidian(summary):
        # Only clear if we are using this script as the primary driver for 2-hour summaries
        # If digest.py also runs, they might fight over clearing the file.
        # But if the user wants "every 2 hours", this script should probably be the one clearing it.
        clear_daily_tweets()
        print("Daily tweets cleared after saving to Obsidian.")

if __name__ == "__main__":
    main()
