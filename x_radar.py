"""Daily X Radar: personalized trends -> focused recent search -> Feishu."""
import json
import math
import os
from datetime import datetime, timedelta, timezone

import requests

import digest

API_ROOT = "https://api.x.com/2"
CORE_QUERIES = [
    '"AI coding" OR "vibe coding" OR Codex',
    '"indie hacker" OR "build in public" OR solopreneur',
    '"AI agent" OR "AI product"',
    "Grok OR Claude OR OpenAI",
]
TOPIC_WORDS = {
    "ai", "artificial intelligence", "coding", "developer", "indie",
    "hacker", "agent", "grok", "codex", "claude", "openai", "saas",
    "productivity", "developer tools", "vibe coding", "solopreneur",
}
SIGNAL_PHRASES = ("i wish there was", "is there a tool that", "does anyone know",
                  "i hate having to", "how do you")


def _get(path, token, params=None):
    response = requests.get(f"{API_ROOT}{path}", headers={"Authorization": f"Bearer {token}"},
                            params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def refresh_access_token():
    """Exchange the long-lived refresh token for a short-lived user token."""
    refresh_token = os.getenv("X_USER_REFRESH_TOKEN")
    client_id = os.getenv("X_CLIENT_ID")
    client_secret = os.getenv("X_CLIENT_SECRET")
    if not refresh_token or not client_id:
        raise RuntimeError("Missing X_USER_REFRESH_TOKEN or X_CLIENT_ID.")
    response = requests.post(
        "https://api.x.com/2/oauth2/token",
        data={"refresh_token": refresh_token, "grant_type": "refresh_token", "client_id": client_id},
        auth=(client_id, client_secret) if client_secret else None,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if response.status_code >= 400:
        try:
            error = response.json()
            detail = error.get("error_description") or error.get("detail") or error.get("error")
        except ValueError:
            detail = response.text[:200]
        raise RuntimeError(
            f"X OAuth token refresh failed (HTTP {response.status_code}): {detail or 'unknown error'}. "
            "Check X_CLIENT_ID, X_CLIENT_SECRET, and X_USER_REFRESH_TOKEN."
        )
    payload = response.json()
    if not payload.get("access_token"):
        raise RuntimeError("X token refresh returned no access token.")
    if payload.get("refresh_token") and payload["refresh_token"] != refresh_token:
        print("WARNING: X returned a rotated refresh token; update X_USER_REFRESH_TOKEN in GitHub Secrets.")
    return payload["access_token"]


def get_personalized_queries(token):
    payload = _get("/users/personalized_trends", token,
                    {"personalized_trend.fields": "trend_name,post_count,trending_since"})
    trends = payload.get("data", [])
    return [t["trend_name"] for t in trends
            if any(word in t.get("trend_name", "").lower() for word in TOPIC_WORDS)]


def search_posts(token, query, max_results=20):
    params = {
        "query": f"({query}) -is:retweet -is:reply",
        "max_results": min(max_results, 100),
        "start_time": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "tweet.fields": "created_at,public_metrics,author_id,lang",
        "expansions": "author_id",
        "user.fields": "name,username,public_metrics",
    }
    return _get("/tweets/search/recent", token, params).get("data", [])


def normalize_posts(posts):
    users = {u["id"]: u for u in posts.pop("includes", {}).get("users", [])} if isinstance(posts, dict) else {}
    rows = posts if isinstance(posts, list) else posts.get("data", [])
    result = []
    for post in rows:
        metrics = post.get("public_metrics", {})
        author = users.get(post.get("author_id"), {})
        score = math.log1p(metrics.get("like_count", 0) + 2 * metrics.get("retweet_count", 0)
                           + metrics.get("reply_count", 0))
        text = post.get("text", "")
        result.append({"id": post["id"], "author": author.get("name", "未知作者"),
                       "username": author.get("username", ""), "text": text,
                       "url": f"https://x.com/{author.get('username', 'i')}/status/{post['id']}",
                       "likes": metrics.get("like_count", 0), "reposts": metrics.get("retweet_count", 0),
                       "replies": metrics.get("reply_count", 0), "score": score,
                       "product_signal": any(p in text.lower() for p in SIGNAL_PHRASES)})
    return result


def build_prompt(posts):
    return """请根据以下 X 帖子写一份中文《X Radar》日报，只使用原文事实，不编造。
分成三栏：🔥 Viral（热度最高）、✍️ Content（适合写 X 的素材）、💡 Product Signal（明确出现用户痛点或工具需求）。
每条包含：作者、原文、链接、点赞/转发/回复、一句话总结、为什么重要、可能的 X 发帖角度。没有证据时写“原文未说明”。

帖子数据：
""" + json.dumps(posts, ensure_ascii=False, indent=2)


def main():
    token = refresh_access_token()
    max_requests = int(os.getenv("X_RADAR_MAX_SEARCH_REQUESTS", "8"))
    queries = list(dict.fromkeys(CORE_QUERIES))
    try:
        queries = list(dict.fromkeys(get_personalized_queries(token) + queries))
    except requests.HTTPError as exc:
        raise RuntimeError(f"Personalized Trends unavailable: {exc}") from exc
    posts = []
    for query in queries[:max_requests]:
        posts.extend(search_posts(token, query, int(os.getenv("X_RADAR_RESULTS_PER_QUERY", "20"))))
    ranked = sorted({p["id"]: p for p in normalize_posts({"data": posts})}.values(),
                    key=lambda p: p["score"], reverse=True)[:10]
    os.makedirs("x_radar", exist_ok=True)
    stamp = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")
    with open(f"x_radar/{stamp}.json", "w", encoding="utf-8") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)
    summary = digest.generate_summary(build_prompt(ranked), os.environ["DEEPSEEK_API_KEY"])
    digest.save_to_obsidian_sync(summary)
    webhook = os.getenv("FEISHU_WEBHOOK_DIGEST") or os.getenv("FEISHU_WEBHOOK")
    if not webhook:
        raise RuntimeError("Missing Feishu webhook; radar result preserved.")
    digest.send_to_feishu(webhook, digest.build_feishu_card(summary, f"X Radar — {stamp}"))


if __name__ == "__main__":
    main()
