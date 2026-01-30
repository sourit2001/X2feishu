import os
import requests
import json
import time
import re

# --- Configuration ---
# User list to monitor (ID from their profile URL)
USERS = ["elonmusk", "sama", "karpathy", "vitalikbuterin"]
LAST_IDS_FILE = "last_ids.json"

def get_feishu_card(author, username, content, link):
    """Builds an interactive Feishu card"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📣 X Monitor: {author}"},
                "template": "orange"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**Author:** {author}\n**Account:** @{username}\n\n**Content:**\n{content}"
                    }
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔗 View Original Tweet"},
                            "type": "primary",
                            "url": link
                        }
                    ]
                }
            ]
        }
    }

def fetch_tweets(username, auth_token, ct0):
    """Fetches tweets using Twitter Syndication API (bypassing RSSHub)"""
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
        # Extract JSON from the __NEXT_DATA__ script tag
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match:
            print(f"Could not find data script for {username}")
            return []
            
        data = json.loads(match.group(1))
        # Navigate to the timeline entries
        # Path: props -> pageProps -> timeline -> entries
        timeline = data.get('props', {}).get('pageProps', {}).get('timeline', {})
        entries = timeline.get('entries', [])
        
        result = []
        for entry in entries:
            # Each entry structure can vary, but usually has a 'content' field with 'tweet'
            content = entry.get('content', {})
            t = content.get('tweet')
            if t:
                result.append({
                    "id": t.get('id_str'),
                    "text": t.get('full_text') or t.get('text', ''),
                    "url": f"https://twitter.com/{username}/status/{t.get('id_str')}",
                    "author": t.get('user', {}).get('name', username)
                })
        return result
    except Exception as e:
        print(f"Error parsing {username}: {e}")
        return []

def main():
    # 1. Try to read history
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

        # First item in 'tweets' list is the latest
        latest_id = tweets[0]['id']
        old_id = last_ids.get(user)

        to_push = []
        if not old_id:
            # Initialization
            print(f"Initializing {user} with latest tweet.")
            to_push = [tweets[0]]
            last_ids[user] = latest_id
        elif latest_id != old_id:
            # Find all new items since old_id
            for t in tweets:
                if t['id'] == old_id:
                    break
                to_push.append(t)
            
            # Update to the absolute latest
            last_ids[user] = latest_id
            print(f"Found {len(to_push)} new tweets for {user}.")
            # Reverse to push oldest first
            to_push.reverse()
        else:
            print(f"No new updates for {user}.")

        # Push to Feishu
        for tweet in to_push:
            payload = get_feishu_card(tweet['author'], user, tweet['text'], tweet['url'])
            res = requests.post(webhook_url, json=payload)
            if res.status_code != 200:
                print(f"Feishu error: {res.text}")
            time.sleep(1) # Rate limiting
            
    # 4. Save progress
    with open(LAST_IDS_FILE, 'w') as f:
        json.dump(last_ids, f, indent=2)

if __name__ == "__main__":
    main()