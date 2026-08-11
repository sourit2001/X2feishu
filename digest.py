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
    """Build a source-grounded, natural-language digest grouped by blogger."""
    prompt = """你是一个做信息整理的编辑助手。请忠实依据下面的 X 推文原文，写一份简洁、自然的中文 brief。

请按博主分组总结本时间段内的 X 推文。

## 要求

1. 不要逐条总结推文。
2. 将同一主题的多条推文融合成一篇短文。
3. 直接说清楚这个博主具体发布了什么、在做什么、提出了什么观点或分享了什么工具。
4. 不要使用项目符号。
5. 不要拆分为“观点”“工具”等小节。
6. 每位博主写 1-3 段自然的短文。推文信息较少时可以少写，不要为了凑字数补充空话。
7. 只有原文明确支持时，才写影响、意义或趋势；不要强行拔高。

## 写作口吻

- 像一个熟悉这个领域的人给朋友做简报，直接、具体、克制。
- 每一段都要增加事实或解释因果，不要追求金句、完整的起承转合或“文章感”。
- 优先使用原文中的人名、产品名、动作和结果；不要把普通转发包装成重大事件。
- 不要编造推文没有提到的场景、动机、心理、对话、数据、案例或行业影响。
- 句子长短自然，避免连续使用相同句式；能用短句说清楚，就不要绕着说。

## 去掉 AI 味

不要使用或变形使用这些套路：
- “这意味着” / “背后反映出” / “正在重塑” / “一场……正在上演”
- “按下暂停键” / “打开了新的想象空间” / “成为重要信号” / “引发深层思考”
- “值得关注的是” / “值得一提的是” / “可以看出” / “不难发现” / “总体来看”
- “从某种意义上说” / “某种程度上” / “归根结底” / “无疑”
- 夸张的标题、宏大比喻、商业黑话、机械的“首先/其次/最后”和重复结论

不要添加“今日深度洞察”“结语”或与原文无关的励志式收束。没有足够材料时，宁可写短，也不要总结大道理。

## 输出格式

每个博主依次输出如下结构：

### @[博主中文名字]

（1-3 段短文；信息少时可以更短）

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

用 200 字以内总结本时间段确实出现的共同主题、新工具或变化。
只有原文存在多个相关事实时才写这一部分；没有共同主题就写“本期没有明显共同主题”。
不要重复前文，不要为了凑出趋势而拔高，不要统计词频。

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

def generate_summary(prompt, api_key, max_attempts=2):
    """Call DeepSeek API with thinking disabled and reject empty output."""
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个克制的中文信息整理编辑。只根据输入的 X 推文写 brief：具体、自然、可追溯；信息少就少写，不编造，不强行升华，不使用 AI 套话、宏大比喻或重复结论。按要求输出博主分组、原文链接和本期趋势。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.6,
                max_tokens=3000,
                extra_body={"thinking": {"type": "disabled"}}
            )

            if not response.choices:
                raise RuntimeError("DeepSeek returned no choices.")

            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", None)
            print(
                f"DeepSeek attempt {attempt}/{max_attempts}: "
                f"finish_reason={finish_reason}, content_chars={len(content.strip())}"
            )

            if content.strip():
                return content.strip()

            last_error = RuntimeError(
                f"DeepSeek returned empty content (finish_reason={finish_reason})."
            )
        except Exception as exc:
            last_error = exc
            print(f"DeepSeek attempt {attempt}/{max_attempts} failed: {exc}")

        if attempt < max_attempts:
            print("Retrying DeepSeek summary generation...")

    raise RuntimeError(
        "DeepSeek failed to generate a non-empty digest; tweet queue preserved."
    ) from last_error

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

def send_to_feishu(webhook_url, payload):
    """Send a digest and verify both HTTP and Feishu business status."""
    response = requests.post(webhook_url, json=payload, timeout=30)
    response.raise_for_status()

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError("Feishu returned a non-JSON response.") from exc

    business_code = result.get("code", result.get("StatusCode"))
    if business_code not in (0, "0"):
        message = result.get("msg", result.get("StatusMessage", "unknown error"))
        raise RuntimeError(
            f"Feishu rejected the digest: code={business_code}, message={message}"
        )

    print(f"Digest pushed to Feishu. HTTP {response.status_code}, code={business_code}")
    return result

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
    if not save_to_obsidian_sync(summary):
        raise RuntimeError("Digest could not be saved; tweet queue preserved.")

    # 2. Push to Feishu
    if not webhook_url:
        raise RuntimeError("Missing FEISHU_WEBHOOK; tweet queue preserved.")

    payload = build_feishu_card(summary, date_str)
    send_to_feishu(webhook_url, payload)

    # 3. Clear only after the report and Feishu delivery both succeeded
    clear_daily_tweets()
    print("Daily tweets cleared.")

if __name__ == "__main__":
    main()
