import requests
import json
import os
import time
from datetime import datetime, timedelta

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
        print(f"Bitable credentials missing: app_token={bool(app_token)}, table_id={bool(table_id)}, token={bool(token)}")
        return None
        
    # Diagnostic: check for extra spaces or weird lengths
    print(f"DEBUG: App Token length={len(app_token)}, Table ID length={len(table_id)}")
    print(f"DEBUG: App Token starts/ends with: {app_token[0]}...{app_token[-1]}")
    print(f"DEBUG: Table ID starts/ends with: {table_id[0]}...{table_id[-1]}")

    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    # Convert pub_time string (YYYY-MM-DD HH:MM) to millisecond timestamp
    # Bitable Date field requires milliseconds
    ts_ms = int(time.time() * 1000) # Default to now
    try:
        # Parse the Beijing time string we formatted earlier
        dt = datetime.strptime(pub_time, '%Y-%m-%d %H:%M')
        # Convert back to UTC timestamp (Beijing is UTC+8, so subtract 8 hours)
        utc_ts = int((dt - timedelta(hours=8)).timestamp())
        ts_ms = utc_ts * 1000
    except Exception as e:
        print(f"Time conversion warning: {e}")

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
            "发布时间": ts_ms, # Successfully identified as needing millisecond timestamp
            "状态": "待处理" # Default status
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=record)
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("code") == 0:
                record_id = res_data.get("data", {}).get("record", {}).get("record_id")
                if record_id:
                    record_url = f"https://www.feishu.cn/base/{app_token}?table={table_id}&record={record_id}"
                    print(f"✅ Bitable Sync Success: {nickname}")
                    return record_url
                return f"https://www.feishu.cn/base/{app_token}?table={table_id}"
            else:
                print(f"❌ Bitable API Error: {res_data.get('code')} - {res_data.get('msg')}")
                if res_data.get("code") == 1254045: # FieldNameNotFound
                    print("🔍 Attempting to fetch correct field names from your table...")
                    fields_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
                    f_resp = requests.get(fields_url, headers=headers)
                    if f_resp.status_code == 200:
                        all_fields = [f.get("field_name") for f in f_resp.json().get("data", {}).get("items", [])]
                        print(f"📋 Your table's actual fields are: {', '.join(all_fields)}")
                        print("💡 Please make sure the keys in bitable_sync.py match these EXACTLY.")
                print(f"Response Detail: {json.dumps(res_data, ensure_ascii=False)}")
        else:
            print(f"❌ Bitable HTTP Failed: {response.status_code}")
            print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"💥 Bitable sync unexpected error: {e}")
    return None
