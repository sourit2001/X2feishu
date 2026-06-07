import os
import requests
import json
import time
import re
import base64
from datetime import datetime, timedelta
from bitable_sync import sync_to_bitable

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
    {"username": "dotey", "nickname": "宝玉"},
    {"username": "emollick", "nickname": "Ethan Mollick"},
    {"username": "rileybrown", "nickname": "Riley Brown"},
    {"username": "vasuman", "nickname": "Vasu"},
    {"username": "godofprompt", "nickname": "God of Prompt"},
    {"username": "venturetwins", "nickname": "Venture Twins"},
    {"username": "a16z", "nickname": "a16z"},
    {"username": "oran_ge", "nickname": "oran_ge"},
    {"username": "tuturetom", "nickname": "TutureTom"},
    {"username": "xiaohu", "nickname": "小虎"},
    {"username": "lijigang", "nickname": "李继刚"},
    {"username": "seclink", "nickname": "seclink"},
    {"username": "icreatelife", "nickname": "icreatelife"},
    {"username": "mreflow", "nickname": "mreflow"},
    {"username": "aleabitoreddit", "nickname": "aleabitoreddit"},
    {"username": "justinsuntron", "nickname": "孙宇晨"},
    {"username": "pmarca", "nickname": "Marc Andreessen"}
]
LAST_IDS_FILE = "last_ids.json"
DAILY_TWEETS_FILE = "daily_tweets.json"
WEB_FEED_DEFAULT_PATH = "data/signals.json"
WEB_FEED_DEFAULT_LIMIT = 80
WEB_FEED_BUILD = "web-feed-timeline-sync-v2"

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

def get_feishu_card(nickname, username, content, link, pub_time, quoted_tweet=None, bitable_url=None):
    """Builds an interactive Feishu card matching user's requested style"""
    body = f"**作者：** {nickname}\n**账号：** @{username}\n**发布时间：** {pub_time}\n\n**推文全文：**\n{content}"

    if quoted_tweet:
        body += f"\n\n💬 **引用 @{quoted_tweet['username']} 的推文：**\n\"{quoted_tweet['text']}\""

    actions = [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "� 查看原推详情"},
            "type": "primary",
            "url": link
        }
    ]

    if bitable_url:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "📌 标记为待办"},
            "type": "default",
            "url": bitable_url
        })

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
                        "content": body
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "action",
                    "actions": actions
                }
            ]
        }
    }

def get_web_feed_usernames():
    """Return usernames that should also be published to the public web feed."""
    raw = os.getenv("WEB_FEED_USERNAMES")
    if not raw:
        return {item["username"].lower() for item in get_web_feed_bloggers()}

    return {
        item.strip().lstrip("@").lower()
        for item in raw.split(",")
        if item.strip()
    }

def get_web_feed_bloggers():
    """Return extra bloggers monitored specifically for the public web feed."""
    raw = os.getenv("WEB_FEED_BLOGGERS") or "aleabitoreddit:Serenity"
    bloggers = []

    for item in raw.split(","):
        if not item.strip():
            continue

        username, _, nickname = item.partition(":")
        username = username.strip().lstrip("@")
        if username:
            bloggers.append({
                "username": username,
                "nickname": nickname.strip() or username
            })

    return bloggers

def get_monitored_bloggers():
    """Combine the existing Feishu monitor list with public web feed accounts."""
    bloggers = []
    seen = set()

    for item in get_web_feed_bloggers() + BLOGGERS:
        username = item["username"].lower()
        if username in seen:
            continue

        seen.add(username)
        bloggers.append(item)

    return bloggers

def get_cashtags(text):
    """Extract stock symbols such as $MU, $LITE, and A-share codes like 688017."""
    value = text or ""
    symbols = set(re.findall(r"\$([A-Z][A-Z0-9]{0,5})\b", value))
    symbols.update(re.findall(r"(?<!\d)(?:[036]\d{5})(?!\d)", value))
    return sorted(symbols)

def get_github_json_file(repo, path, branch, headers):
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    response = requests.get(url, headers=headers, params={"ref": branch}, timeout=30)

    if response.status_code == 404:
        return None, {"updatedAt": None, "sources": [], "tweets": []}

    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload.get("content", "")).decode("utf-8")
    return payload.get("sha"), json.loads(content)

def put_github_json_file(repo, path, branch, headers, sha, content):
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    body = {
        "message": "Update Serenity web feed",
        "content": base64.b64encode(
            json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8"),
        "branch": branch,
    }

    if sha:
        body["sha"] = sha

    response = requests.put(url, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    return response

def sync_to_web_feed(tweet_record):
    """Publish selected tweets to the Track Serenity website repository."""
    token = re.sub(r"[\s\r\n\t]+", "", os.getenv("WEB_FEED_GITHUB_TOKEN") or "")
    repo = (os.getenv("WEB_FEED_REPO") or "sourit2001/trackserenity").strip()
    branch = (os.getenv("WEB_FEED_BRANCH") or "main").strip()
    path = (os.getenv("WEB_FEED_PATH") or WEB_FEED_DEFAULT_PATH).strip()
    limit = int(os.getenv("WEB_FEED_LIMIT") or WEB_FEED_DEFAULT_LIMIT)
    target_usernames = get_web_feed_usernames()
    username = tweet_record.get("username", "").lower()

    if username not in target_usernames:
        return

    if not token or not repo:
        print("Web feed credentials missing; skipping website sync.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        sha, feed = get_github_json_file(repo, path, branch, headers)
        tweets = feed.get("tweets", [])
        tweet_id = tweet_record.get("id_str")

        if any(item.get("id") == tweet_id for item in tweets):
            print(f"Web feed already has tweet: {tweet_id}")
            return

        tweets.insert(0, {
            "id": tweet_id,
            "username": tweet_record.get("username"),
            "nickname": tweet_record.get("nickname"),
            "author": tweet_record.get("nickname"),
            "text": tweet_record.get("text"),
            "url": tweet_record.get("url"),
            "createdAt": tweet_record.get("created_at", ""),
            "displayTime": tweet_record.get("time", ""),
            "quotedTweet": tweet_record.get("quoted_tweet"),
            "isRetweet": tweet_record.get("is_retweet", False),
            "cashtags": get_cashtags(tweet_record.get("text", "")),
        })

        feed["updatedAt"] = datetime.utcnow().isoformat() + "Z"
        feed["sources"] = [
            {"username": item["username"], "nickname": item["nickname"]}
            for item in get_web_feed_bloggers()
            if item["username"].lower() in target_usernames
        ]
        feed["tweets"] = tweets[:limit]

        put_github_json_file(repo, path, branch, headers, sha, feed)
        print(f"Synced to web feed: {tweet_id}")
    except Exception as e:
        print(f"Web feed sync failed: {e}")

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
                # --- EXTRACT FULL TEXT ---
                # Check for Note Tweet (X Premium long tweets)
                note_text = t.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {}).get('text')
                text = note_text if note_text else (t.get('full_text') or t.get('text', ''))

                # Check for Quote Tweet (retweet with comment)
                quoted = t.get('quoted_tweet')
                quoted_info = None
                if quoted:
                    qt_note = quoted.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {}).get('text')
                    qt_text = qt_note if qt_note else (quoted.get('full_text') or quoted.get('text', ''))
                    quoted_info = {
                        "author": quoted.get('user', {}).get('name', '未知'),
                        "username": quoted.get('user', {}).get('screen_name', ''),
                        "text": qt_text
                    }

                # Detection of Retweet
                is_retweet = False
                if t.get('retweeted_status'):
                    is_retweet = True
                elif text.startswith('RT @'):
                    is_retweet = True
                elif t.get('user', {}).get('screen_name', '').lower() != username.lower():
                    is_retweet = True

                result.append({
                    "id": int(t.get('id_str')),
                    "id_str": t.get('id_str'),
                    "text": text,
                    "url": f"https://twitter.com/{username}/status/{t.get('id_str')}",
                    "author": t.get('user', {}).get('name', username),
                    "created_at": t.get('created_at'),
                    "quoted_tweet": quoted_info,
                    "is_retweet": is_retweet
                })
        # Sort by ID descending
        result.sort(key=lambda x: x['id'], reverse=True)
        return result
    except Exception as e:
        print(f"Error parsing {username}: {e}")
        return []

def should_force_web_feed_test():
    return (os.getenv("FORCE_WEB_FEED_TEST") or "").lower() in {"1", "true", "yes"}

def run_web_feed_test(auth_token, ct0):
    """Publish recent configured web-feed tweets without touching Feishu or last_ids."""
    target_usernames = get_web_feed_usernames()
    limit = int(os.getenv("WEB_FEED_TEST_LIMIT") or 20)
    tested = False

    for blogger in get_web_feed_bloggers():
        user = blogger["username"]
        nick = blogger["nickname"]

        if user.lower() not in target_usernames:
            continue

        tested = True
        print(f"--- Force web feed test: {nick} (@{user}) ---")
        tweets = fetch_tweets(user, auth_token, ct0)

        if not tweets:
            print("No tweets found for web feed test.")
            continue

        print(f"Publishing up to {limit} recent tweets for web feed test.")
        for tweet in reversed(tweets[:limit]):
            daily_record = {
                "username": user,
                "nickname": nick,
                "text": tweet["text"],
                "quoted_tweet": tweet.get("quoted_tweet"),
                "url": tweet["url"],
                "time": format_time(tweet["created_at"]),
                "created_at": tweet.get("created_at"),
                "id_str": tweet["id_str"],
                "is_retweet": tweet.get("is_retweet", False)
            }
            sync_to_web_feed(daily_record)

    if not tested:
        print("No matching web feed users configured for test.")

def main():
    print(f"WEB_FEED_BUILD={WEB_FEED_BUILD}")

    if os.path.exists(LAST_IDS_FILE):
        with open(LAST_IDS_FILE, 'r') as f:
            last_ids = json.load(f)
    else:
        last_ids = {}

    if os.path.exists(DAILY_TWEETS_FILE):
        with open(DAILY_TWEETS_FILE, 'r') as f:
            daily_tweets = json.load(f)
    else:
        daily_tweets = []

    auth_token = os.getenv("TWITTER_AUTH_TOKEN")
    ct0 = os.getenv("TWITTER_CT0")
    webhook_url = os.getenv("FEISHU_WEBHOOK")

    if not (auth_token and ct0 and webhook_url):
        print("Error: Missing credentials or webhook URL.")
        return

    if should_force_web_feed_test():
        run_web_feed_test(auth_token, ct0)
        return

    print("Syncing web feed accounts before general monitor pass.")
    run_web_feed_test(auth_token, ct0)

    for blogger in get_monitored_bloggers():
        user = blogger['username']
        nick = blogger['nickname']
        print(f"--- Checking {nick} (@{user}) ---")
        tweets = fetch_tweets(user, auth_token, ct0)
        
        if not tweets:
            continue

        if user.lower() == "aleabitoreddit" or user.lower() in get_web_feed_usernames():
            web_limit = int(os.getenv("WEB_FEED_TIMELINE_LIMIT") or os.getenv("WEB_FEED_LIMIT") or WEB_FEED_DEFAULT_LIMIT)
            print(f"Syncing recent web feed timeline for {user}.")
            for tweet in reversed(tweets[:web_limit]):
                web_record = {
                    "username": user,
                    "nickname": nick,
                    "text": tweet['text'],
                    "quoted_tweet": tweet.get('quoted_tweet'),
                    "url": tweet['url'],
                    "time": format_time(tweet['created_at']),
                    "created_at": tweet.get('created_at'),
                    "id_str": tweet['id_str'],
                    "is_retweet": tweet.get('is_retweet', False)
                }
                sync_to_web_feed(web_record)
                time.sleep(0.2)

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
            
            # Filter Elon Musk's retweets for real-time push
            # Only push if it's NOT a retweet OR it's NOT Elon Musk
            should_push = True
            if user.lower() == "elonmusk" and tweet.get('is_retweet'):
                should_push = False
            
            if should_push:
                # Sync to Bitable first to get the record URL
                bitable_url = sync_to_bitable(nick, user, tweet['text'], tweet['url'], pub_time)
                
                payload = get_feishu_card(nick, user, tweet['text'], tweet['url'], pub_time, tweet.get('quoted_tweet'), bitable_url)
                requests.post(webhook_url, json=payload)
                print(f"Pushed to Feishu: {tweet['id_str']}")
            else:
                print(f"Skipping real-time push for {nick}'s retweet: {tweet['id_str']}")

            # Save to daily tweets for digest
            daily_record = {
                "username": user,
                "nickname": nick,
                "text": tweet['text'],
                "quoted_tweet": tweet.get('quoted_tweet'),
                "url": tweet['url'],
                "time": pub_time,
                "created_at": tweet.get('created_at'),
                "id_str": tweet['id_str'],
                "is_retweet": tweet.get('is_retweet', False)
            }
            daily_tweets.append(daily_record)
            sync_to_web_feed(daily_record)
            time.sleep(1)

    with open(LAST_IDS_FILE, 'w') as f:
        json.dump(last_ids, f, indent=2)

    with open(DAILY_TWEETS_FILE, 'w') as f:
        json.dump(daily_tweets, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
