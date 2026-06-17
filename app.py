import os
import sys
import sqlite3

from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)

from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

from google import genai
from google.genai import types

# =========================
# Flask
# =========================

app = Flask(__name__)

# =========================
# Environment Variables
# =========================

LINE_CHANNEL_ACCESS_TOKEN = os.getenv(
    "LINE_CHANNEL_ACCESS_TOKEN"
)

LINE_CHANNEL_SECRET = os.getenv(
    "LINE_CHANNEL_SECRET"
)

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

if not LINE_CHANNEL_ACCESS_TOKEN:
    raise ValueError(
        "LINE_CHANNEL_ACCESS_TOKEN not found"
    )

if not LINE_CHANNEL_SECRET:
    raise ValueError(
        "LINE_CHANNEL_SECRET not found"
    )

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found"
    )

# =========================
# LINE
# =========================

line_config = Configuration(
    access_token=LINE_CHANNEL_ACCESS_TOKEN
)

handler = WebhookHandler(
    LINE_CHANNEL_SECRET
)

# =========================
# Gemini
# =========================

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)

# =========================
# SQLite
# =========================

DB_FILE = "f1_assistant.db"


def init_db():

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def save_chat(user_id, role, message):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO chat_logs
        (user_id, role, message)
        VALUES (?, ?, ?)
        """,
        (user_id, role, message)
    )

    conn.commit()
    conn.close()


def get_recent_history(user_id, limit=8):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role,message
        FROM chat_logs
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit)
    )

    rows = cursor.fetchall()

    conn.close()

    rows.reverse()

    return rows


init_db()

# =========================
# F1 Prompt
# =========================

F1_SYSTEM_INSTRUCTION = """
你是一位專業的 F1 賽車（一級方程式）AI 教學助理。

規則：

1. /提示
不要直接給答案。
請給 1~2 個引導提示。

2. /筆記
將內容整理成：
- 重點
- 專有名詞
- 核心觀念

3. /學習計畫
提供 3 天或 5 天學習規劃。

4. /來點刺激的
分享 F1 歷史冷知識。

5. 一般問題
直接回答。
回答控制在 100~200 字內。

回答請簡潔、專業、
適合 LINE 閱讀。
"""

# =========================
# Callback
# =========================

@app.route("/callback", methods=["POST"])
def callback():

    signature = request.headers.get(
        "X-Line-Signature"
    )

    body = request.get_data(
        as_text=True
    )

    try:

        handler.handle(
            body,
            signature
        )

    except InvalidSignatureError:

        abort(400)

    return "OK"


# =========================
# Message Handler
# =========================

@handler.add(
    MessageEvent,
    message=TextMessageContent
)
def handle_text_message(event):

    if event.reply_token == \
       "00000000000000000000000000000000":
        return

    user_id = getattr(
        event.source,
        "user_id",
        "unknown"
    )

    user_text = event.message.text

    try:

        save_chat(
            user_id,
            "user",
            user_text
        )

        history = get_recent_history(
            user_id,
            limit=8
        )

        context = ""

        for role, msg in history:

            context += (
                f"{role}: {msg}\n"
            )

        prompt = f"""
最近聊天紀錄：

{context}

使用者最新問題：

{user_text}
"""

        response = (
            gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        F1_SYSTEM_INSTRUCTION
                    ),
                    temperature=0.7,
                    max_output_tokens=800
                )
            )
        )

        ai_reply = getattr(
            response,
            "text",
            None
        )

        if not ai_reply:

            ai_reply = (
                "🏎️ 暫時無法產生回覆，請稍後再試。"
            )

        if len(ai_reply) > 4500:

            ai_reply = (
                ai_reply[:4500]
                + "\n\n...(內容過長已截斷)"
            )

        save_chat(
            user_id,
            "assistant",
            ai_reply
        )

    except Exception as e:

        print(
            f"Gemini Error: {e}",
            file=sys.stderr
        )

        ai_reply = (
            "🏎️ 系統引擎過熱中，請稍後再試！"
        )

    try:

        with ApiClient(
            line_config
        ) as api_client:

            messaging_api = MessagingApi(
                api_client
            )

            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=str(ai_reply)
                        )
                    ]
                )
            )

    except Exception as line_error:

        print(
            f"LINE Reply Error: {line_error}",
            file=sys.stderr
        )


# =========================
# Main
# =========================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
```
