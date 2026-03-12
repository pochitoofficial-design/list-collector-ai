import os
import time
import uuid
from datetime import datetime
import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# .envファイルから環境変数を読み込む
load_dotenv()

# デフォルトのGoogle Maps APIキーの取得（.envの内容があれば反映、なければ空文字）
DEFAULT_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
if DEFAULT_API_KEY == "YOUR_API_KEY_HERE":
    DEFAULT_API_KEY = ""

# APIのエンドポイント (Places API New)
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


def get_places_new(query: str, max_results: int, api_key: str) -> list:
    """
    Google Maps Places API (New) を使用して場所情報を取得する。
    """
    places = []
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # 取得したいフィールドを明示的に指定（名前、住所、電話番号、WebサイトURL）
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,nextPageToken",
    }
    
    # 日本語の結果を取得する設定を含める
    payload = {
        "textQuery": query,
        "languageCode": "ja",
        "pageSize": 20 # 1ページあたりの件数(最大20)
    }

    next_page_token = None
    
    # Streamlit用の進捗バー
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while len(places) < max_results:
        if next_page_token:
            payload["pageToken"] = next_page_token
            time.sleep(2) # 念のためウェイト
            
        try:
            response = requests.post(TEXT_SEARCH_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"ネットワークエラーが発生しました: {e}")
            if e.response is not None:
                st.error(f"ステータスコード: {e.response.status_code}")
                st.error(f"レスポンス: {e.response.text}")
            break
        except ValueError:
            st.error("APIからのレスポンスをJSONとして解析できませんでした。")
            break

        results = data.get("places", [])
        
        if not results and not places:
            st.warning("検索結果は見つかりませんでした。条件を変えてお試しください。")
            break
            
        places.extend(results)
        
        # 進捗状況の更新
        current_len = min(len(places), max_results)
        progress = current_len / max_results
        progress_bar.progress(progress)
        status_text.text(f"取得中... ({current_len}/{max_results} 件)")
        
        if len(places) >= max_results:
            places = places[:max_results]
            break
            
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
            
    # 完了時にプログレスバーとステータステキストをクリア
    progress_bar.empty()
    status_text.empty()
            
    return places


def format_data(places_data: list) -> list:
    """
    APIレスポンスから必要な情報を抽出し、整形する。
    """
    collected_list = []
    
    for place in places_data:
        display_name_obj = place.get("displayName", {})
        service_name = display_name_obj.get("text", "")
        company_name = service_name
        
        address = place.get("formattedAddress", "")
        phone = place.get("nationalPhoneNumber", "-")
        website = place.get("websiteUri", "-")
        
        collected_list.append({
            "サービス名（店舗名）": service_name,
            "会社名": company_name,
            "住所": address,
            "電話番号": phone,
            "WebサイトURL": website
        })
        
    return collected_list


def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """
    DataframeをBOM付きのUTF-8 CSVに変換する（Excelでの文字化け防止用）
    """
    return df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')


def show_sidebar():
    """
    履歴とゴミ箱を含んだサイドバーの表示ロジック
    """
    # ====== APIキー設定セクション ======
    st.sidebar.markdown("### 🔑 API設定")
    ui_api_key = st.sidebar.text_input(
        "Google Maps APIキー",
        value=DEFAULT_API_KEY,
        type="password"
    )
    st.sidebar.markdown("[📝 APIキーの取得方法](https://console.cloud.google.com/apis/credentials)")
    
    # 料金や利用上の注意に関するExpanderを表示（小さめの文字）
    with st.sidebar.expander("💡 料金・ご利用について"):
        st.markdown(
            """
            <div style="font-size: 0.85em; color: #888;">
            ・APIキーはご自身のGoogle Cloudのものを使用してください<br>
            ・Places APIの料金目安：20件取得で約$0.06（約9円）<br>
            ・月$200までは無料枠内で利用可能です<br>
            ・使いすぎ防止のため1回の取得は最大60件までです<br>
            ・APIキーの利用状況は<a href="https://console.cloud.google.com/apis/dashboard" target="_blank">Google Cloud Console</a>で確認できます
            </div>
            """, 
            unsafe_allow_html=True
        )

    st.sidebar.markdown("---")
    
    # ====== リスト管理セクション ======
    st.sidebar.title("📁 リスト管理")
    
    st.sidebar.markdown("### ⏱️ 履歴")
    if not st.session_state.history:
        st.sidebar.caption("保存された履歴はありません")
    else:
        # 新しい順に表示
        for item in reversed(st.session_state.history):
            with st.sidebar.expander(f"📌 {item['query']} ({item['date_str']})"):
                st.caption(f"📍 取得件数: {len(item['data'])}件")
                
                # ボタンの横並べ
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("👁️ 表示", key=f"view_{item['id']}", use_container_width=True):
                        st.session_state.selected_history_id = item['id']
                        st.rerun()
                with col2:
                    if st.button("🗑️ 削除", key=f"del_{item['id']}", use_container_width=True):
                        # 履歴から消してゴミ箱へ
                        st.session_state.history.remove(item)
                        st.session_state.trash.append(item)
                        if st.session_state.selected_history_id == item['id']:
                            st.session_state.selected_history_id = None
                        st.rerun()
                        
    st.sidebar.markdown("---")
    
    st.sidebar.markdown("### 🗑️ ゴミ箱")
    if not st.session_state.trash:
        st.sidebar.caption("ゴミ箱は空です")
    else:
        for item in reversed(st.session_state.trash):
            with st.sidebar.expander(f"🗑️ {item['query']} ({item['date_str']})"):
                st.caption(f"📍 取得件数: {len(item['data'])}件")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("♻️ 復元", key=f"res_{item['id']}", use_container_width=True):
                        st.session_state.trash.remove(item)
                        st.session_state.history.append(item)
                        st.rerun()
                with col2:
                    if st.button("❌ 完消", key=f"perm_{item['id']}", use_container_width=True):
                        st.session_state.trash.remove(item)
                        st.rerun()

    return ui_api_key


def main():
    st.set_page_config(page_title="営業リスト収集ツール", layout="centered", page_icon="🏢")

    # ユーザー指示により、Streamlitのデフォルトメニュー・フッター・ヘッダー等を非表示
    st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    [data-testid="stToolbar"] {display: none;}
    </style>
    """, unsafe_allow_html=True)
    
    # --------------------------------
    # セッションステートの初期化
    # --------------------------------
    if "history" not in st.session_state:
        st.session_state.history = []
    if "trash" not in st.session_state:
        st.session_state.trash = []
    if "selected_history_id" not in st.session_state:
        st.session_state.selected_history_id = None

    # サイドバーの表示（APIキーを受け取る）
    ui_api_key = show_sidebar()
    
    # UIの微調整
    st.markdown("""
        <style>
        /* デフォルトのStreamlit要素を非表示にする */
        #MainMenu {visibility: hidden;}            /* 右上のハンバーガーメニュー */
        footer {visibility: hidden;}              /* Made with Streamlit のフッター */
        header {visibility: hidden;}              /* 右上のデプロイメニュー周りのヘッダー */
        .stDeployButton {display: none;}          /* デプロイボタン（念のため個別指定） */
        .css-1rs6os {visibility: hidden;}         /* GitHubアイコンなどを含むツールバー */

        /* 入力時の「Enterキーを押して...」という文字を隠す（文字被り防止） */
        div[data-testid="InputInstructions"] {
            display: none !important;
        }
        /* フォームのパディングを整える */
        [data-testid="stForm"] {
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("🏢 営業リスト収集ツール")
    st.markdown("Google Mapsを用いて業種・地域から企業情報を収集します。")
    
    # メイン画面（履歴表示 or 検索フォーム）
    if st.session_state.selected_history_id:
        # 履歴項目の表示モード
        selected_item = next((i for i in st.session_state.history if i["id"] == st.session_state.selected_history_id), None)
        
        if selected_item:
            st.info(f"💾 履歴からのデータ表示: **{selected_item['query']}** （取得日: {selected_item['date_str']})")
            
            df = pd.DataFrame(selected_item["data"])
            st.dataframe(df, use_container_width=True)
            
            csv_data = convert_df_to_csv(df)
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.download_button(
                    label="📥 CSVをダウンロード",
                    data=csv_data,
                    file_name=selected_item["filename"],
                    mime="text/csv",
                    type="primary",
                    key="history_dl_btn"
                )
            with col2:
                if st.button("⬅️ 新しく検索する", use_container_width=True):
                    st.session_state.selected_history_id = None
                    st.rerun()
                    
            # 履歴表示中は検索フォームを出さずに終了
            return
            
    # 検索モード
    st.markdown("### 🔍 検索条件")
    with st.form("search_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            industry = st.text_input("業種", placeholder="例：カフェ、美容室")
        
        with col2:
            region = st.text_input("地域", placeholder="例：渋谷区、大阪市")
            
        st.markdown("<br>", unsafe_allow_html=True)
        max_results = st.slider("取得件数（最大）", min_value=10, max_value=60, value=30, step=10)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # APIキーが未入力の場合はボタンを非活性にする
        is_disabled = not bool(ui_api_key)
        submitted = st.form_submit_button("🔍 リストを取得する", disabled=is_disabled, use_container_width=True)

    if is_disabled:
        st.warning("左側のサイドバーでGoogle Maps APIキーを入力してください。")

    if submitted:
        if not industry or not region:
            st.error("業種と地域の両方を入力してください。")
            return
            
        search_query = f"{region} {industry}"
        st.info(f"「{search_query}」を検索中...")
        
        # 検索の実行
        with st.spinner("Google Mapsからデータを取得しています..."):
            places_data = get_places_new(search_query, max_results, ui_api_key)
            
        if places_data:
            # データの整形
            formatted_data = format_data(places_data)
            df = pd.DataFrame(formatted_data)
            
            st.success(f"🎉 合計 {len(formatted_data)} 件の情報を取得しました！")
            
            # --- 履歴に保存 ---
            date_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            file_date = datetime.now().strftime("%Y%m%d")
            filename = f"{industry}_{region}_{file_date}.csv"
            
            history_item = {
                "id": str(uuid.uuid4()),
                "query": search_query,
                "date_str": date_str,
                "filename": filename,
                "data": formatted_data
            }
            # セッションステート配列の末尾（新しい順では先頭）に追加
            st.session_state.history.append(history_item)
            
            # テーブル表示
            st.dataframe(df, use_container_width=True)
            
            # CSVダウンロードボタンの表示
            csv_data = convert_df_to_csv(df)
            
            st.download_button(
                label="📥 CSVをダウンロード",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                type="primary",
                key="new_dl_btn"
            )


if __name__ == "__main__":
    main()
