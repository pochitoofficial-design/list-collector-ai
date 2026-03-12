import os
import sys
import csv
import time
from datetime import datetime
import requests
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# Google Maps APIキーの取得
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
    print("エラー: .envファイルに有効なGOOGLE_MAPS_API_KEYが設定されていません。")
    sys.exit(1)

# APIのエンドポイント (Places API New)
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

def get_places_new(query: str, max_results: int = 60) -> list:
    """
    Google Maps Places API (New) を使用して場所情報を取得する。
    """
    places = []
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        # 取得したいフィールドを明示的に指定（名前、住所、電話番号、WebサイトURL）
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,nextPageToken",
    }
    
    # 日本語の結果を取得する設定を含める
    payload = {
        "textQuery": query,
        "languageCode": "ja",
        "pageSize": 20 # 1ページあたりの件数(最大20)
    }

    print(f"「{query}」で検索を開始します...")
    
    next_page_token = None
    
    while len(places) < max_results:
        if next_page_token:
            payload["pageToken"] = next_page_token
            print("次のページを読み込んでいます...")
            time.sleep(2) # 念のためウェイト
            
        try:
            response = requests.post(TEXT_SEARCH_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"ネットワークエラーが発生しました: {e}")
            if e.response is not None:
                print(f"ステータスコード: {e.response.status_code}")
                print(f"レスポンス: {e.response.text}")
            break
        except ValueError:
            print("APIからのレスポンスをJSONとして解析できませんでした。")
            break

        results = data.get("places", [])
        
        if not results and not places:
            print("検索結果は見つかりませんでした。")
            break
            
        places.extend(results)
        
        if len(places) >= max_results:
            places = places[:max_results]
            break
            
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
            
    return places

def main():
    print("=== Google Maps 営業リスト収集ツール ===")
    
    # ユーザー入力
    industry = input("業種を入力してください（例：カフェ、美容室等）: ").strip()
    region = input("地域を入力してください（例：渋谷区、大阪市等）: ").strip()
    
    if not industry or not region:
        print("エラー: 業種と地域は両方入力してください。")
        sys.exit(1)
        
    search_query = f"{region} {industry}"
    max_results_limit = 60
    
    # 検索実行
    places_data = get_places_new(search_query, max_results_limit)
    
    if not places_data:
        print("取得できるデータがありませんでした。処理を終了します。")
        sys.exit(0)
        
    print(f"\n合計 {len(places_data)} 件の情報を取得しました。データを整形します...")
    
    collected_list = []
    
    # データの抽出
    for idx, place in enumerate(places_data, 1):
        # Places API (New) のレスポンス構造に合わせる
        display_name_obj = place.get("displayName", {})
        service_name = display_name_obj.get("text", "")
        company_name = service_name
        
        address = place.get("formattedAddress", "")
        phone = place.get("nationalPhoneNumber", "-")
        website = place.get("websiteUri", "-")
        
        print(f"[{idx}/{len(places_data)}] 処理中: {service_name}")
        
        collected_list.append({
            "サービス名（店舗名）": service_name,
            "会社名": company_name,
            "住所": address,
            "電話番号": phone,
            "WebサイトURL": website
        })

        
    # CSVに出力
    # ファイル名: 業種_地域_日付.csv
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{industry}_{region}_{date_str}.csv"
    
    # 保存先ディレクトリの準備（カレントディレクトリ）
    filepath = os.path.join(os.getcwd(), filename)
    
    print("\nCSVファイルを出力しています...")
    try:
        with open(filepath, mode="w", encoding="utf-8-sig", newline="") as f:
            fieldnames = ["サービス名（店舗名）", "会社名", "住所", "電話番号", "WebサイトURL"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in collected_list:
                writer.writerow(row)
                
        print(f"\n処理完了! {len(collected_list)} 件のデータを保存しました。")
        print(f"出力ファイル: {filepath}")
    except IOError as e:
        print(f"ファイルの書き込み中にエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
