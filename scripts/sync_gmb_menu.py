import glob
import json
import os
import sys
import requests

CLIENT_ID = os.environ.get("GMB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GMB_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GMB_REFRESH_TOKEN")
LOCATION_ID = os.environ.get("GMB_LOCATION_ID")  # 例: locations/1234567890123456789


def get_access_token():
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    res = requests.post(token_url, data=data)
    if res.status_code != 200:
        print(f"❌ トークン取得エラー (Status {res.status_code}): {res.text}")
        sys.exit(1)
    return res.json()["access_token"]


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

        # 価格の数値をクレンジング (文字列の数字にする)
        if isinstance(price_val, (int, float)):
            units = str(int(price_val))
        elif isinstance(price_val, str):
            units = "".join(filter(str.isdigit, price_val)) or "0"
        else:
            units = "0"

        if name:
            parsed_items.append({
                "labels": [
                    {
                        "displayName": name[:140],
                        "description": desc[:1000],
                        "languageCode": "ja"
                    }
                ],
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
        items = parse_json_file(fpath)
        print(f"📖 {fpath} から {len(items)} 件のアイテムを読み込みました")
        cena_items.extend(items)

    if cena_items:
        sections.append({
            "labels": [
                {
                    "displayName": "ディナーコース (Dinner)",
                    "languageCode": "ja"
                }
            ],
            "items": cena_items
        })

    # 2. ドリンク
    if os.path.exists("drink.json"):
        drink_items = parse_json_file("drink.json")
        print(f"🍷 drink.json から {len(drink_items)} 件のドリンクを読み込みました")
        if drink_items:
            sections.append({
                "labels": [
                    {
                        "displayName": "ドリンク (Drinks)",
                        "languageCode": "ja"
                    }
                ],
                "items": drink_items
            })

    return {
        "menus": [
            {
                "labels": [
                    {
                        "displayName": "Gran GIOIA メニュー",
                        "languageCode": "ja"
                    }
                ],
                "sections": sections,
            }
        ]
    }


def sync_to_gmb():
    access_token = get_access_token()
    
    # LOCATION_ID の表記揺れ（locations/有無）を自動補正
    loc_id_clean = LOCATION_ID.strip()
    if not loc_id_clean.startswith("locations/"):
        loc_id_clean = f"locations/{loc_id_clean}"

    # My Business Business Information API v1 の標準エンドポイント
    url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{loc_id_clean}/foodMenus"
    
    payload = build_menu_payload()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    print(f"🚀 送信先URL: {url}")
    print(f"📦 送信データ概要: セクション数 {len(payload['menus'][0]['sections'])}")

    response = requests.patch(url, headers=headers, json=payload)

    if response.status_code == 200:
        print("🎉【大成功】Google Business Profile へのメニュー同期が完了しました！")
    else:
        print(f"\n❌ エラー発生 (Status Code: {response.status_code})")
        print(f"📄 Googleからの返答詳細:\n{response.text}\n")
        sys.exit(1)


if __name__ == "__main__":
    sync_to_gmb()
