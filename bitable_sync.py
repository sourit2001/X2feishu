import requests
import json
import os
import time

def get_tenant_access_token():
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    
    if not app_id or not app_secret:
        return None
        
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return response.json().get("tenant_access_token")
    except Exception as e:
        print(f"Error getting token: {e}")
    return None

def sync_to_bitable(nickname, username, content, link, pub_time):
    app_token = os.getenv("BITABLE_APP_TOKEN")
    table_id = os.getenv("BITABLE_TABLE_ID")
    token = get_tenant_access_token()
    
    if not (app_token and table_id and token):
        print("Bitable credentials missing, skipping sync.")
        return False
        
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    # Map to Bitable fields. 
    # Important: Field names must match EXACTLY what's in the table.
    # Defaulting to common names, user might need to adjust their table.
    record = {
        "fields": {
            "博主": nickname,
            "账号": f"@{username}",
            "内容": content,
            "详情链接": {
                "link": link,
                "text": "查看原文"
            },
            "发布时间": pub_time,
            "状态": "待处理" # Default status
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=record)
        if response.status_code == 200:
            record_id = response.json().get("data", {}).get("record", {}).get("record_id")
            if record_id:
                record_url = f"https://www.feishu.cn/base/{app_token}?table={table_id}&record={record_id}"
                print(f"Synced to Bitable: {nickname}, Record URL: {record_url}")
                return record_url
            return f"https://www.feishu.cn/base/{app_token}?table={table_id}"
        else:
            print(f"Bitable sync failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error syncing to Bitable: {e}")
    return None
