import glob
import json
import os
import requests

# GitHub Secretsから認証情報を取得
CLIENT_ID = os.environ.get("GMB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GMB_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GMB_REFRESH_TOKEN")
LOCATION_ID = os.environ.get("GMB_LOCATION_ID")  # 例: locations/1234567890


def get_access_token():
    """リフレッシュトークンから最新アクセストークンを発行"""
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


def parse_json_file(file_path):
    """各JSONファイルを読み込み、GMB API用のアイテムフォーマットに変換"""
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 配列か単一オブジェクトかを判定
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = data.get("items", [data])
    else:
        raw_items = []

    parsed_items = []
    for item in raw_items:
        # JSON内の多様なキー名（title, name, courseNameなど）に対応
        name = (
            item.get("title")
            or item.get("name")
            or item.get("courseName")
            or ""
        )
        desc = (
            item.get("description")
            or item.get("detail")
            or item.get("lead")
            or ""
        )
        price_val = item.get("price", 0)

        # 価格数値を文字列にクレンジング
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
                        "displayName": name[:140],  # GMB制限: 最大140文字
                        "description": desc[:1000],  # GMB制限: 最大1000文字
                    }
                ],
                "price": {"currencyCode": "JPY", "units": units},
            })

    return parsed_items


def build_menu_payload():
    """Cena と Drink のみを一括統合したペイロードを作成"""
    sections = []

    # 1. ディナーコース (CENA: cenaa.json, cenab.json, etc.)
    cena_files = sorted(glob.glob("cena*.json"))
    cena_items = []
    for fpath in cena_files:
        cena_items.extend(parse_json_file(fpath))

    if cena_items:
        sections.append(
            {"labels": [{"displayName": "Dinner Courses"}], "items": cena_items}
        )

    # 2. ドリンク (DRINK: drink.json)
    if os.path.exists("drink.json"):
        drink_items = parse_json_file("drink.json")
        if drink_items:
            sections.append(
                {"labels": [{"displayName": "Drinks"}], "items": drink_items}
            )

    # 3. ランチコース (LUNCH) 🌟 将来運用開始するときは以下のコメント（#）を解除してください
    # lunch_files = sorted(glob.glob("lunch*.json"))
    # lunch_items = []
    # for fpath in lunch_files:
    #     lunch_items.extend(parse_json_file(fpath))
    # if lunch_items:
    #     sections.append({
    #         "labels": [{"displayName": "Lunch Courses"}],
    #         "items": lunch_items
    #     })

    return {
        "menus": [
            {
                "labels": [{"displayName": "Gran GIOIA Menu"}],
                "sections": sections,
            }
        ]
    }


def sync_to_gmb():
    access_token = get_access_token()
    payload = build_menu_payload()

    url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{LOCATION_ID}/foodMenus"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.patch(url, headers=headers, json=payload)

    if response.status_code == 200:
        print(
            "✅ Google Business Profile へのメニュー完全同期が完了しました！"
        )
    else:
        print(f"❌ 同期エラー (Status: {response.status_code})")
        print(response.text)


if __name__ == "__main__":
    sync_to_gmb()
