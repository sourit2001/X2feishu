import os
import requests
import json
import time
import re
from datetime import datetime, timedelta

# --- Configuration ---
# User list to monitor (ID from their profile URL)
BLOGGERS = [
    {"username": "elonmusk", "nickname": "马斯克"},
    {"username": "sama", "nickname": "奥特曼"},
    {"username": "vitalikbuterin", "nickname": "V神"},
    {"username": "karpathy", "nickname": "卡帕斯"},
    {"username": "op7418", "nickname": "归藏"},
    {"username": "drfeifei", "nickname": "李飞飞"},
    {"username": "lexfridman", "nickname": "Lex"},
    {"username": "dotey", "nickname": "宝玉"}
]
LAST_IDS_FILE = "last_ids.json"

def format_time(time_str):
    """Converts Twitter's created_at to Beijing Time (UTC+8)"""
    try:
        # Twitter format example: "Sat Jan 31 00:00:00 +0000 2026"
        dt = datetime.strptime(time_str, '%a %b %d %H:%M:%S +0000 %Y')
        # To Beijing Time
        beijing_dt = dt + timedelta(hours=8)
        return beijing_dt.strftime('%Y-%m-%d %H:%M')
    except:
        return time_str

def get_feishu_card(nickname, username, content, link, pub_time):
    """Builds an interactive Feishu card matching user's requested style"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🐦 X (Twitter) 监控动态"},
                "template": "orange"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**作者：** {nickname}\n**账号：** @{username}\n**发布时间：** {pub_time}\n\n**推文全文：**\n{content}"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🚀 查看原推详情"},
                            "type": "primary",
                            "url": link
                        }
                    ]
                }
            ]
        }
    }

def fetch_tweets(username, auth_token, ct0):
    """Fetches tweets using Twitter Syndication API with support for Note Tweets (long tweets)"""
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Cookie": f"auth_token={auth_token}; ct0={ct0}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"Failed to fetch {username}: HTTP {response.status_code}")
            return []
            
        html = response.text
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match:
            return []
            
        data = json.loads(match.group(1))
        timeline = data.get('props', {}).get('pageProps', {}).get('timeline', {})
        entries = timeline.get('entries', [])
        
        result = []
        for entry in entries:
            content = entry.get('content', {})
            t = content.get('tweet')
            if t:
                # --- EXTACT FULL TEXT ---
                # Check for Note Tweet (X Premium long tweets)
                note_text = t.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {}).get('text')
                text = note_text if note_text else (t.get('full_text') or t.get('text', ''))
                
                result.append({
                    "id": int(t.get('id_str')),
                    "id_str": t.get('id_str'),
                    "text": text,
                    "url": f"https://twitter.com/{username}/status/{t.get('id_str')}",
                    "author": t.get('user', {}).get('name', username),
                    "created_at": t.get('created_at')
                })
        # Sort by ID descending
        result.sort(key=lambda x: x['id'], reverse=True)
        return result
    except Exception as e:
        print(f"Error parsing {username}: {e}")
        return []

def main():
    if os.path.exists(LAST_IDS_FILE):
        with open(LAST_IDS_FILE, 'r') as f:
            last_ids = json.load(f)
    else:
        last_ids = {}

    auth_token = os.getenv("TWITTER_AUTH_TOKEN")
    ct0 = os.getenv("TWITTER_CT0")
    webhook_url = os.getenv("FEISHU_WEBHOOK")

    if not (auth_token and ct0 and webhook_url):
        print("Error: Missing credentials or webhook URL.")
        return

    for blogger in BLOGGERS:
        user = blogger['username']
        nick = blogger['nickname']
        print(f"--- Checking {nick} (@{user}) ---")
        tweets = fetch_tweets(user, auth_token, ct0)
        
        if not tweets:
            continue

        max_id = max(t['id'] for t in tweets)
        old_id = int(last_ids.get(user, 0))

        to_push = []
        if old_id == 0:
            print(f"Initializing {user} with latest tweet: {max_id}")
            to_push = [tweets[0]]
            last_ids[user] = str(max_id)
        elif max_id > old_id:
            for t in tweets:
                if t['id'] > old_id:
                    to_push.append(t)
                else:
                    break
            
            print(f"Found {len(to_push)} new updates for {user}.")
            last_ids[user] = str(max_id)
            to_push.reverse()
        else:
            print(f"No new updates.")

        for tweet in to_push:
            pub_time = format_time(tweet['created_at'])
            payload = get_feishu_card(nick, user, tweet['text'], tweet['url'], pub_time)
            requests.post(webhook_url, json=payload)
            print(f"Pushed: {tweet['id_str']}")
            time.sleep(1)
            
    with open(LAST_IDS_FILE, 'w') as f:
        json.dump(last_ids, f, indent=2)

if __name__ == "__main__":
    main()