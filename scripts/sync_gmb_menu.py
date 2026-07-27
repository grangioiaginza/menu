import glob
import json
import os
import sys
import requests

CLIENT_ID = os.environ.get("GMB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GMB_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GMB_REFRESH_TOKEN")
LOCATION_ID = os.environ.get("GMB_LOCATION_ID")  # 例: locations/1234567890... または 1234567890...


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


def get_account_name(access_token):
    """Google Business Profile のアカウントID (accounts/XXXXXXXX) を自動取得"""
    url = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get(url, headers=headers)

    if res.status_code == 403:
        print(
            "\n❌【要設定】Google Cloud Console で 'My Business Account Management"
            " API' を有効化してください。"
        )
        print(
            "GCP (https://console.cloud.google.com/) ➔ ライブラリ ➔ 'My Business"
            " Account Management API' を検索して「有効にする」を押します。\n"
        )
        sys.exit(1)
    elif res.status_code != 200:
        print(f"❌ アカウントID取得エラー (Status {res.status_code}): {res.text}")
        sys.exit(1)

    accounts = res.json().get("accounts", [])
    if not accounts:
        print("❌ Google Business Profile のアカウントが見つかりませんでした。")
        sys.exit(1)

    return accounts[0]["name"]  # 例: "accounts/10987654321"


def clean_price(price_val):
    """'2,000-' や 18000 などの価格表現を整数数値へ安全に変換"""
    if isinstance(price_val, (int, float)):
        return int(price_val)
    elif isinstance(price_val, str):
        digits = "".join(filter(str.isdigit, price_val))
        return int(digits) if digits else 0
    return 0


def parse_course_json(file_path):
    """cena*.json などのコース料理データから「お品書き構成」を抽出して作成"""
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    parsed_items = []

    # パターン1: courseName, price, dishes を持つの構造（ご共有いただいたサンプル形式）
    if isinstance(data, dict) and "courseName" in data:
        course_name = data.get("courseName", "")
        price = clean_price(data.get("price", 0))
        dishes = data.get("dishes", [])

        dish_lines = []
        for d in dishes:
            cat = d.get("category", "")
            title = d.get("title", "")
            is_prefix = d.get("isPrefix", False)
            options = d.get("options", [])

            line = f"【{cat}】{title}"
            if is_prefix and options:
                opt_titles = [
                    o.get("title", "") for o in options if o.get("title")
                ]
                if opt_titles:
                    # 選択肢を最大3つまで概要に表示
                    opts_str = ", ".join(opt_titles[:3])
                    line += f"（{opts_str} 等から選択）"
            dish_lines.append(line)

        description = "\n".join(dish_lines)

        if course_name:
            parsed_items.append({
                "labels": [
                    {
                        "displayName": str(course_name)[:140],
                        "description": str(description)[:1000],
                        "languageCode": "ja",
                    }
                ],
                "attributes": {
                    "price": {"currencyCode": "JPY", "units": price}
                },
            })

    # パターン2: 汎用配列構造（その他のケース用フォールバック）
    else:
        raw_items = data if isinstance(data, list) else data.get("items", [data])
        for item in raw_items:
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
            price = clean_price(item.get("price", 0))

            if name:
                parsed_items.append({
                    "labels": [
                        {
                            "displayName": str(name)[:140],
                            "description": str(desc)[:1000],
                            "languageCode": "ja",
                        }
                    ],
                    "attributes": {
                        "price": {"currencyCode": "JPY", "units": price}
                    },
                })

    return parsed_items


def parse_drink_json():
    """drink.json の categories 構造を綺麗にセクション分けして解析"""
    if not os.path.exists("drink.json"):
        return []

    with open("drink.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    categories = data.get("categories", [])
    drink_sections = []

    for cat in categories:
        cat_name = cat.get("name_ja") or cat.get("name_en") or "ドリンク"
        cat_items = cat.get("items", [])
        parsed_items = []

        for item in cat_items:
            name = item.get("name", "")
            desc = item.get("description", "")
            opt_note = item.get("option_note", "")
            price = clean_price(item.get("price", 0))

            full_desc = f"{desc}\n{opt_note}".strip() if opt_note else desc

            if name:
                parsed_items.append({
                    "labels": [
                        {
                            "displayName": str(name)[:140],
                            "description": str(full_desc)[:1000],
                            "languageCode": "ja",
                        }
                    ],
                    "attributes": {
                        "price": {"currencyCode": "JPY", "units": price}
                    },
                })

        if parsed_items:
            drink_sections.append({
                "labels": [{"displayName": str(cat_name), "languageCode": "ja"}],
                "items": parsed_items,
            })

    return drink_sections


def build_menu_payload():
    sections = []

    # 1. ディナーコース (CENA)
    cena_files = sorted(glob.glob("cena*.json"))
    cena_items = []
    for fpath in cena_files:
        items = parse_course_json(fpath)
        print(f"📖 {fpath} から {len(items)} 件のコースを読み込みました")
        cena_items.extend(items)

    if cena_items:
        sections.append({
            "labels": [
                {"displayName": "ディナーコース (Dinner)", "languageCode": "ja"}
            ],
            "items": cena_items,
        })

    # 2. ドリンク (DRINK - カテゴリーごとにセクション分割)
    drink_sections = parse_drink_json()
    total_drinks = sum(len(s["items"]) for s in drink_sections)
    print(
        f"🍷 drink.json から {len(drink_sections)} カテゴリー / 計 {total_drinks}"
        " 件のドリンクを読み込みました"
    )

    sections.extend(drink_sections)

    return {
        "menus": [
            {
                "labels": [
                    {"displayName": "Gran GIOIA メニュー", "languageCode": "ja"}
                ],
                "sections": sections,
            }
        ]
    }


def sync_to_gmb():
    access_token = get_access_token()
    account_name = get_account_name(access_token)

    loc_id_clean = LOCATION_ID.replace("locations/", "").strip()
    url = f"https://mybusiness.googleapis.com/v4/{account_name}/locations/{loc_id_clean}/foodMenus"

    payload = build_menu_payload()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    print(f"🚀 送信先アカウント: {account_name}")
    print(f"🚀 送信先URL: {url}")
    print(f"📦 総セクション数: {len(payload['menus'][0]['sections'])} 個")

    response = requests.patch(url, headers=headers, json=payload)

    if response.status_code == 200:
        print("🎉【大成功】Google Business Profile へのメニュー全同期が完了しました！")
    else:
        print(f"\n❌ エラー発生 (Status Code: {response.status_code})")
        print(f"📄 Googleからの返答詳細:\n{response.text}\n")
        sys.exit(1)


if __name__ == "__main__":
    sync_to_gmb()
