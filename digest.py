import os
import json
import requests
from datetime import datetime, timedelta
from openai import OpenAI

DAILY_TWEETS_FILE = "daily_tweets.json"


def load_daily_tweets():
    """Load accumulated tweets from the daily tweets file"""
    if os.path.exists(DAILY_TWEETS_FILE):
        with open(DAILY_TWEETS_FILE, 'r') as f:
            return json.load(f)
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


def build_summary_prompt(groups):
    """Build the prompt for DeepSeek to generate a summary"""
    prompt = """你是一个专业的社交媒体分析师。请根据以下各博主在 X (Twitter) 上发布的最新推文，生成一份中文简报。

要求：
1. 首先提炼出 3-5 条最重要、最值得关注的要点（跨所有博主），**请在每个要点末尾附上最相关的推文链接，格式为 [🔗](链接)**
2. 然后按博主分组，每个博主用 1-3 句话总结其推文内容
3. **在每个博主的总结段落末尾，按顺序列出该博主今日所有推文的完整链接，格式为：[推文1](链接), [推文2](链接)...**
4. 如果推文包含引用转发（quoted_tweet），请结合原推和评论一起理解，说明谁引用了谁的观点
5. 语言简洁有力，像新闻简报一样。输出使用中文。

以下是推文数据：

"""
    for nick, group in groups.items():
        prompt += f"\n--- {nick} (@{group['username']}) 共 {len(group['tweets'])} 条 ---\n"
        for i, t in enumerate(group['tweets'], 1):
            rt_tag = "(转帖) " if t.get('is_retweet') else ""
            prompt += f"\n[推文{i} - {t['time']}] {rt_tag}{t['text']}\n链接: {t['url']}"
            if t.get('quoted_tweet'):
                qt = t['quoted_tweet']
                prompt += f"\n  └─ 引用 @{qt['username']}: {qt['text']}"
            prompt += "\n"

    prompt += """

请严格按以下格式输出（使用飞书 Markdown 语法）：

🔥 **今日要点**
1. [要点1] [🔗](url)
2. [要点2] [🔗](url)
...

👤 **各博主动态**

🐦 **[博主昵称]** (@username) — X条
[总结内容]
[推文1](url), [推文2](url)...

🐦 **[博主昵称]** (@username) — X条
[总结内容]
[推文1](url), [推文2](url)...
"""
    return prompt


def generate_summary(prompt, api_key):
    """Call DeepSeek API to generate summary"""
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你是一个专业的社交媒体分析师，擅长从推文中提炼关键信息并生成简洁的中文简报。输出使用飞书 Markdown 格式。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.3,
        max_tokens=2000
    )

    return response.choices[0].message.content


def build_feishu_digest_card(summary, total_tweets, total_bloggers, date_str, time_range):
    """Build a Feishu card for the daily digest"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📋 X (Twitter) 简报 — {date_str}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📊 **概览**\n共监控 **{total_bloggers}** 位博主，本时间段内共发布 **{total_tweets}** 条推文"
                    }
                },
                {"tag": "hr"},
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
                        "content": f"⏰ 统计时段：{time_range}\n🤖 摘要由 DeepSeek 生成"
                    }
                }
            ]
        }
    }


def main():
    # Load environment variables
    api_key = os.getenv("DEEPSEEK_API_KEY")
    webhook_url = os.getenv("FEISHU_WEBHOOK")

    if not api_key or not webhook_url:
        print("Error: Missing DEEPSEEK_API_KEY or FEISHU_WEBHOOK.")
        return

    # Load tweets
    tweets = load_daily_tweets()

    # Date info (Beijing time)
    now = datetime.utcnow() + timedelta(hours=8)
    date_str = now.strftime('%Y-%m-%d')
    yesterday = now - timedelta(days=1)
    time_range = f"{yesterday.strftime('%m-%d %H:%M')} ~ {now.strftime('%m-%d %H:%M')}"

    if not tweets:
        print("No tweets to summarize. Sending empty digest.")
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"📋 X (Twitter) 简报 — {date_str}"},
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"📭 过去 4 小时内没有监控到新的推文动态。\n\n⏰ 统计时段：{time_range}"
                        }
                    }
                ]
            }
        }
        requests.post(webhook_url, json=payload)
        return

    # Group tweets by blogger
    groups = group_tweets_by_blogger(tweets)

    # Batch bloggers to avoid hitting context/output limits
    blogger_nicknames = list(groups.keys())
    batch_size = 5
    all_summaries = []
    
    # Calculate stats
    total_tweets = len(tweets)
    total_bloggers = len(groups)
    
    print(f"Generating digest for {total_tweets} tweets from {total_bloggers} bloggers in batches...")
    
    for i in range(0, total_bloggers, batch_size):
        batch_nicks = blogger_nicknames[i:i + batch_size]
        batch_groups = {nick: groups[nick] for nick in batch_nicks}
        
        print(f"Processing batch {i//batch_size + 1}: {', '.join(batch_nicks)}")
        prompt = build_summary_prompt(batch_groups)
        
        # Adjust prompt for subsequent batches if needed, but for now, we just want summaries
        batch_summary = generate_summary(prompt, api_key)
        all_summaries.append(batch_summary)
        
    # Combine summaries (DeepSeek usually returns the formatted card content)
    # We'll merge them by stripping the "今日要点" from later batches if they repeat, 
    # but for simplicity and safety, we combine the relevant sections.
    final_summary = "\n\n".join(all_summaries)
    
    print(f"All batches processed successfully.")

    # Build and send Feishu card
    payload = build_feishu_digest_card(final_summary, total_tweets, total_bloggers, date_str, time_range)
    response = requests.post(webhook_url, json=payload)
    print(f"Digest pushed to Feishu. Status: {response.status_code}")

    # Clear daily tweets after successful push
    clear_daily_tweets()
    print("Daily tweets cleared.")


if __name__ == "__main__":
    main()
