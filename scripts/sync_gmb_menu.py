import glob
import json
import os
import sys
import requests

CLIENT_ID = os.environ.get("GMB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GMB_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GMB_REFRESH_TOKEN")
LOCATION_ID = os.environ.get("GMB_LOCATION_ID")  # 例: locations/1234567890


def get_access_token():
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    res = requests.post(token_url, data=data)
    res.raise_for_status()
    return res.json()["access_token"]


def get_account_id(access_token):
    """Googleアカウントに紐づく Account ID (accounts/xxx) を自動取得"""
    url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    accounts = res.json().get("accounts", [])
    if not accounts:
        print("❌ Google Business Profile のアカウントが見つかりません。")
        sys.exit(1)
    # 最初のアカウントIDを返す
    return accounts[0]["name"]


def parse_json_file(file_path):
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = data.get("items", [data])
    else:
        raw_items = []

    parsed_items = []
    for item in raw_items:
        name = item.get("title") or item.get("name") or item.get("courseName") or ""
        desc = item.get("description") or item.get("detail") or item.get("lead") or ""
        price_val = item.get("price", 0)

        if isinstance(price_val, (int, float)):
            units = int(price_val)
        elif isinstance(price_val, str):
            units = int("".join(filter(str.isdigit, price_val)) or "0")
        else:
            units = 0

        if name:
            # v4 API の正しいフォーマット（labelsはオブジェクト、価格は attributes 内）
            parsed_items.append({
                "labels": {
                    "displayName": name[:140],
                    "description": desc[:1000],
                    "languageCode": "ja"
                },
                "attributes": {
                    "price": {
                        "currencyCode": "JPY",
                        "units": units
                    }
                }
            })

    return parsed_items


def build_menu_payload():
    sections = []

    # 1. ディナーコース
    cena_files = sorted(glob.glob("cena*.json"))
    cena_items = []
    for fpath in cena_files:
        cena_items.extend(parse_json_file(fpath))

    if cena_items:
        sections.append({
            "labels": {
                "displayName": "ディナーコース (Dinner)",
                "languageCode": "ja"
            },
            "items": cena_items
        })

    # 2. ドリンク
    if os.path.exists("drink.json"):
        drink_items = parse_json_file("drink.json")
        if drink_items:
            sections.append({
                "labels": {
                    "displayName": "ドリンク (Drinks)",
                    "languageCode": "ja"
                },
                "items": drink_items
            })

    return {
        "menus": [
            {
                "labels": {
                    "displayName": "Gran GIOIA メニュー",
                    "languageCode": "ja"
                },
                "sections": sections,
            }
        ]
    }


def sync_to_gmb():
    # 1. トークンとアカウントIDの取得
    access_token = get_access_token()
    account_name = get_account_id(access_token)
    
    # 2. API v4 用の正しいURLを構築 (accounts/xxx/locations/yyy/foodMenus)
    # LOCATION_ID が "locations/123" などの形式であることを考慮して結合
    location_id_clean = LOCATION_ID.replace("locations/", "")
    full_resource_name = f"{account_name}/locations/{location_id_clean}/foodMenus"
    
    url = f"https://mybusiness.googleapis.com/v4/{full_resource_name}"
    
    payload = build_menu_payload()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # 3. v4 API へ PATCH 送信
    response = requests.patch(url, headers=headers, json=payload)

    if response.status_code == 200:
        print("✅ Google Business Profile へのメニュー完全同期が完了しました！")
    else:
        print(f"❌ 同期エラー (Status: {response.status_code})")
        print(response.text)
        sys.exit(1) # これを入れることで失敗時はGitHub Actionsが赤色で止まります


if __name__ == "__main__":
    sync_to_gmb()
