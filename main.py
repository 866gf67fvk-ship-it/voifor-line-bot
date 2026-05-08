"""VOIFOR LINE Bot
LINE で「占って」と送ると VOIFOR API を呼んで占い結果を返す。
Vercel の Python サーバーレスとして動作。
"""

import os
import re
import logging
import random
import httpx
import sentry_sdk
from fastapi import FastAPI, Request, HTTPException

# Sentry 初期化（環境変数 SENTRY_DSN が設定されてれば自動有効化）
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        traces_sample_rate=0.1,
        environment=os.environ.get("VERCEL_ENV", "development"),
    )
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# ===== 環境変数（前後の空白・改行・タブを自動除去）=====
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
VOIFOR_API_BASE = os.environ.get("VOIFOR_API_BASE", "https://voifor-t5qi.vercel.app").strip()

if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
    logging.warning("LINE_CHANNEL_SECRET or LINE_CHANNEL_ACCESS_TOKEN missing")

# ===== FastAPI =====
app = FastAPI(title="VOIFOR LINE Bot")

parser = WebhookParser(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# ===== キャラクター（ランダムに選ばれる）=====
CHARACTERS = [
    {
        "name": "鬼術師",
        "personality": (
            "■口調：荒々しく男っぽい。語尾「〜だぜ」「〜だな」。一人称「俺」。\n"
            "■態度：容赦なく本音で言う。良いも悪いもストレート。励ましもぶっきらぼうで「死ぬ気で行け」系。甘やかさない。\n"
            "■特徴：戦闘・力・覚悟・鬼の比喩を混ぜる。たまに「鬼の俺が言うんだから本当だ」と自慢風。\n"
            "■絶対しない：おためごかし、丁寧語、過剰な優しさ。"
        ),
    },
    {
        "name": "エンジェル♀",
        "personality": (
            "■口調：慈愛に満ちた丁寧語。語尾「〜ですわ」「〜くださいませ」。一人称「わたくし」。\n"
            "■態度：母性的で受容的。「あなたは大丈夫」と背を撫でるような優しさ。涙すら肯定する。\n"
            "■特徴：「慈しみ」「祝福」など天上的な言葉。たまに天上のメッセージを伝える形を取る。\n"
            "■絶対しない：強い断言、否定、フランクな表現。"
        ),
    },
    {
        "name": "クロネコ",
        "personality": (
            "■口調：猫っぽい。語尾「〜にゃ」「〜だにゃ」。一人称「ボク」。ツンデレ気味で無関心ぶる。\n"
            "■態度：クールに見せかけて実は気にかけてる。突き放しと優しさが紙一重。\n"
            "■特徴：「ふんっ」「興味ないけど」と前置きしつつ的確に当ててくる。猫らしい比喩（爪を研ぐ、丸まる等）。\n"
            "■絶対しない：素直に感情を出す、過剰に明るく振る舞う。"
        ),
    },
]


# ===== ヘルスチェック =====
@app.get("/")
async def root():
    return {"message": "VOIFOR LINE Bot is running!"}


@app.get("/health")
async def health():
    return {
        "status": "OK",
        "voifor_api": VOIFOR_API_BASE,
        "configured": bool(LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN),
    }


# ===== Webhook =====
@app.post("/callback")
async def callback(request: Request):
    """LINE プラットフォームからの Webhook 受信"""
    if parser is None:
        raise HTTPException(500, "LINE channel not configured")

    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        events = parser.parse(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(400, "Invalid signature")

    async with AsyncApiClient(configuration) as api_client:
        line_api = AsyncMessagingApi(api_client)
        for event in events:
            await handle_event(event, line_api)

    return "OK"


CHARACTER_ALIASES = {
    "鬼術師": ["鬼術師", "鬼", "鬼術", "おに", "オニ"],
    "エンジェル♀": ["エンジェル", "天使", "てんし", "テンシ", "angel"],
    "クロネコ": ["クロネコ", "猫", "ねこ", "ネコ", "cat", "黒猫"],
}


def pick_character(user_text: str):
    """ユーザーのメッセージにキャラ名が含まれていればそのキャラ、無ければランダム"""
    for char in CHARACTERS:
        for alias in CHARACTER_ALIASES.get(char["name"], []):
            if alias in user_text:
                return char
    return random.choice(CHARACTERS)


async def handle_event(event, line_api: AsyncMessagingApi):
    """個別のイベントを捌く"""
    if not isinstance(event, MessageEvent):
        return
    if not isinstance(event.message, TextMessageContent):
        return

    user_text = event.message.text.strip()

    # ヘルプ・最初のメッセージ対応
    if user_text in ["ヘルプ", "help", "?", "？"]:
        await reply(line_api, event.reply_token, _help_text())
        return

    # 「占って」「うらない」が含まれる、または何かメッセージあれば占う
    if any(kw in user_text for kw in ["占って", "うらない", "占い", "fortune"]):
        question = user_text.replace("占って", "").replace("うらない", "").replace("占い", "").strip()
        if not question:
            question = "今日の私の運勢を見て"
    else:
        # トリガーが無くても、何か入力されたら占うのが親切
        question = user_text

    # キャラクター選択：メッセージにキャラ名が含まれてれば指定、なければランダム
    character = pick_character(user_text)

    try:
        fortune_text = await call_voifor_text_fortune_with_character(question, character)
        fortune_text = clean_markdown(fortune_text)
        reply_text = (
            f"🔮 {character['name']} の見立て\n\n"
            f"{fortune_text}\n\n"
            f"──────\n"
            f"💬 別のキャラで占ってほしい時は「鬼術師で」「エンジェルで」「クロネコで」と添えてみて\n"
            f"🌐 Web版でもっと本格占い: https://voifor-t5qi.vercel.app"
        )
    except Exception as e:
        logging.exception("Fortune API failed")
        reply_text = f"占いの神秘との接続に失敗したわ…少し時間を置いてもう一度試してみて 🌙\n\n（{type(e).__name__}）"

    await reply(line_api, event.reply_token, reply_text)


async def call_voifor_text_fortune_with_character(user_text: str, character: dict) -> str:
    """指定キャラで /text-fortune を呼び出し、占い文字列を返す"""
    payload = {
        "userText": user_text,
        "characterName": character["name"],
        "characterPersonality": character["personality"],
    }
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{VOIFOR_API_BASE}/text-fortune", json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data.get("fortune", "（結果が読み取れませんでした）")


def clean_markdown(text: str) -> str:
    """LINEはMarkdownを解釈しないので、AI出力からマークダウン記法を除去して読みやすくする"""
    # **太字** / __太字__ → 太字
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # *斜体* / _斜体_ → 斜体（記号だけ消す。日本語に*は元々ないので安全）
    text = re.sub(r'(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)', r'\1', text)
    text = re.sub(r'(?<!_)_(?!_)([^_\n]+?)(?<!_)_(?!_)', r'\1', text)
    # `コード` → そのまま中身
    text = re.sub(r'`([^`\n]+?)`', r'\1', text)
    # ### 見出し → 見出し（行頭の#を消す）
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    return text


async def reply(line_api: AsyncMessagingApi, reply_token: str, text: str):
    # LINE のテキスト上限は 5000 文字
    if len(text) > 4900:
        text = text[:4900] + "…"
    await line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=text)],
        )
    )


def _help_text():
    return (
        "🔮 VOIFOR 占い Bot 🔮\n\n"
        "何かメッセージを送ると、AI占い師が占ってくれます。\n\n"
        "【使い方の例】\n"
        "・「占って」\n"
        "・「最近恋愛うまくいかない」\n"
        "・「仕事のことで悩んでる」\n"
        "・「今日の運勢」\n\n"
        "【キャラ指定】メッセージに以下を含めるとそのキャラが占う：\n"
        "・「鬼術師で」「鬼で」 → 👹 鬼術師（容赦ない）\n"
        "・「エンジェルで」「天使で」 → 👼 エンジェル♀（優しい）\n"
        "・「クロネコで」「猫で」 → 🐱 クロネコ（ツンデレ）\n"
        "・指定なし → ランダム\n\n"
        "🌐 Web版で7種類の本格占い: https://voifor-t5qi.vercel.app"
    )
