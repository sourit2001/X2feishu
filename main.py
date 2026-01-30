import os
import requests
import json
import time

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

def clean_html(html):
    """Simple HTML tag removal"""
    import re
    if not html:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html).strip()

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
        # Use a reliable public RSSHub instance or a local one if accessible
        # Since this runs on GitHub, we use rsshub.app or similar
        url = f"https://rsshub.app/twitter/user/{user}?format=json"
        headers = {
            "Cookie": f"auth_token={auth_token}; ct0={ct0}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                print(f"Failed to fetch {user}: HTTP {response.status_code}")
                continue
                
            data = response.json()
            items = data.get("items", [])
            if not items:
                print(f"No items found for {user}.")
                continue

            # First item is the latest
            latest_id = items[0].get("id")
            old_id = last_ids.get(user)

            if not old_id:
                # Initialization: push the latest one
                print(f"Initializing {user} with latest ID.")
                to_push = [items[0]]
                last_ids[user] = latest_id
            elif latest_id != old_id:
                # Find all new items since old_id
                to_push = []
                for item in items:
                    if item.get("id") == old_id:
                        break
                    to_push.append(item)
                
                # Update to the absolute latest
                last_ids[user] = latest_id
                print(f"Found {len(to_push)} new tweets for {user}.")
                # Reverse to push oldest first
                to_push.reverse()
            else:
                print(f"No new updates for {user}.")
                to_push = []

            # Push to Feishu
            for item in to_push:
                content = clean_html(item.get("summary") or item.get("content_html") or item.get("title"))
                # Truncate content if too long for Feishu
                if len(content) > 1000:
                    content = content[:1000] + "..."
                    
                payload = get_feishu_card(user, user, content, item.get("url"))
                res = requests.post(webhook_url, json=payload)
                if res.status_code != 200:
                    print(f"Feishu error: {res.text}")
                time.sleep(1) # Rate limiting
                
        except Exception as e:
            print(f"Error processing {user}: {e}")

    # 4. Save progress
    with open(LAST_IDS_FILE, 'w') as f:
        json.dump(last_ids, f, indent=2)

if __name__ == "__main__":
    main()
