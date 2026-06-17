import os
import sys
import csv
from datetime import datetime
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from google import genai
from google.genai import types

app = Flask(__name__)

# === 直接填入你提供的密鑰 ===
LINE_CHANNEL_ACCESS_TOKEN = "LmReeyRqWoQbwFCBQyMmkc1d4MVEHBRsJsHUd6nHtr69WSE3ev+9W1Tpe3ixoUYiGkqiA3tBjhuBbM1bvZSWnYiMIh8ocisKBujsSx+piDqT7JtAdCfejYYAED4Ts/lxmxl1T1ApBKDxrd/hAveZVgdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "d6db7e24e858b02efa7ac18283551c10"
GEMINI_API_KEY = "AIzaSyBUZGheV72YshPC0w5m10G_2P1Z1YE2fpM"

# 初始化 LINE 和 Gemini
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# 核心系統 Prompt 設計：F1 賽車教學助理人設
F1_SYSTEM_INSTRUCTION = """
你是一位專業的 F1 賽車（一級方程式）AI 教學助理。你的目標是協助學生學習 F1 的科學、歷史與工程知識。
請依據以下三種情境來引導學習：
1. 【整理筆記】：當學生輸入大量 F1 資訊時，幫他結構化整理成精簡的筆記（包含：專有名詞、核心觀念）。
2. 【解題提示】：當學生詢問 F1 相關問題（如：DRS 原理、輪胎策略、下壓力等），「千萬不要直接給答案」，而是給予 1~2 個引導式的提示（Hint），鼓勵他主動思考。
3. 【學習計畫安排】：當學生想了解 F1 某個領域，幫他規劃一個由淺入深的 3 天或 5 天學習小計畫。

請保持熱情、專業，多使用賽車相關的生動比喻（如：進站、起跑線、格子旗），回答要簡潔，適合 LINE 手機介面閱讀。
"""

# 定義儲存紀錄的函式（存成 CSV 格式，最方便你交作業分析）
def log_chat(user_id, role, message):
    file_exists = os.path.isfile("chat_log.csv")
    with open("chat_log.csv", mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            # 如果檔案不存在，先寫入欄位名稱
            writer.writerow(["時間", "使用者ID", "角色", "訊息內容"])
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([current_time, user_id, role, message])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Check your channel access token/channel secret.")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, content_type=TextMessageContent)
def handle_text_message(event):
    user_id = event.source.user_id
    user_text = event.message.text

    try:
        # === A. 紀錄學生提問 ===
        log_chat(user_id, "student", user_text)

        # === B. 呼叫 Gemini API ===
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=F1_SYSTEM_INSTRUCTION,
                temperature=0.7
            )
        )
        ai_reply = response.text

        # === C. 紀錄 AI 回應 ===
        log_chat(user_id, "ai", ai_reply)

    except Exception as e:
        print(f"Error logic: {e}", file=sys.stderr)
        ai_reply = "系統引擎過熱中（發生錯誤），請稍後再試！"

    # === D. 回傳給 LINE 使用者 ===
    with ApiClient(line_config) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=ai_reply)]
            )
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
