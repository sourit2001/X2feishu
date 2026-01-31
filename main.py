import os
import requests
import json
import time
import re
from datetime import datetime, timedelta

# --- Configuration ---
# User list to monitor (ID from their profile URL)
USERS = ["elonmusk", "sama", "karpathy", "vitalikbuterin"]
LAST_IDS_FILE = "last_ids.json"

def format_time(time_str):
    """Converts Twitter's created_at to Beijing Time (UTC+8)"""
    try:
        # Twitter format example: "Sat Jan 31 00:00:00 +0000 2026"
        dt = datetime.strptime(time_str, '%a %b %d %H:%M:%S +0000 %Y')
        # To Beijing Time
        beijing_dt = dt + timedelta(hours=8)
        return beijing_dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return time_str

def get_feishu_card(author, username, content, link, pub_time):
    """Builds an interactive Feishu card matching n8n style"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🐦 X 监控助手"},
                "template": "orange"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**作者：** {author}\n**账号：** @{username}\n**发布时间：** {pub_time}\n\n**完整内容：**\n{content}"
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
                            "text": {"tag": "plain_text", "content": "🔗 点击查看详情"},
                            "type": "primary",
                            "url": link
                        }
                    ]
                }
            ]
        }
    }

def fetch_tweets(username, auth_token, ct0):
    """Fetches tweets using Twitter Syndication API with robust error handling"""
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
                result.append({
                    "id": t.get('id_str'),
                    "text": t.get('full_text') or t.get('text', ''),
                    "url": f"https://twitter.com/{username}/status/{t.get('id_str')}",
                    "author": t.get('user', {}).get('name', username),
                    "created_at": t.get('created_at')
                })
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

    if not webhook_url:
        print("Error: FEISHU_WEBHOOK not set.")
        return

    for user in USERS:
        print(f"Checking @{user}...")
        tweets = fetch_tweets(user, auth_token, ct0)
        
        if not tweets:
            print(f"No tweets found or error for {user}.")
            continue

        # Check latest non-pinned tweet to update LAST_ID
        latest_id = tweets[0]['id']
        old_id = last_ids.get(user)

        to_push = []
        if not old_id:
            # First initialization: Push the latest one and record
            print(f"Initializing {user} with latest tweet.")
            to_push = [tweets[0]]
            last_ids[user] = latest_id
        elif latest_id != old_id:
            # Find new items
            found_old = False
            for t in tweets:
                if t['id'] == old_id:
                    found_old = True
                    break
                to_push.append(t)
            
            # If we didn't find the old_id (maybe deleted or too many tweets), 
            # we just push the latest and reset and avoid mass pushing
            if not found_old:
                 print(f"Warning: Last ID for {user} not found in current fetch. Pushing latest.")
                 to_push = [tweets[0]]
            
            last_ids[user] = latest_id
            to_push.reverse()
        else:
            print(f"No new updates for {user}.")

        for tweet in to_push:
            pub_time = format_time(tweet['created_at'])
            payload = get_feishu_card(tweet['author'], user, tweet['text'], tweet['url'], pub_time)
            requests.post(webhook_url, json=payload)
            time.sleep(1)
            
    with open(LAST_IDS_FILE, 'w') as f:
        json.dump(last_ids, f, indent=2)

if __name__ == "__main__":
    main()