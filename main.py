"""VOIFOR LINE Bot
LINE で「占って」と送ると VOIFOR API を呼んで占い結果を返す。
Vercel の Python サーバーレスとして動作。
"""

import os
import logging
import random
import httpx
from fastapi import FastAPI, Request, HTTPException
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

# ===== 環境変数 =====
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
VOIFOR_API_BASE = os.environ.get("VOIFOR_API_BASE", "https://voifor-t5qi.vercel.app")

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


async def handle_event(event, line_api: AsyncMessagingApi):
    """個別のイベントを捌く"""
    if not isinstance(event, MessageEvent):
        return
    if not isinstance(event.message, TextMessageContent):
        return

    user_text = event.message.text.strip()

    # 「占って」「うらない」が含まれる、または何かメッセージあれば占う
    if any(kw in user_text for kw in ["占って", "うらない", "占い", "fortune"]):
        question = user_text.replace("占って", "").replace("うらない", "").replace("占い", "").strip()
        if not question:
            question = "今日の私の運勢を見て"
    else:
        # トリガーが無くても、何か入力されたら占うのが親切
        question = user_text

    # ヘルプ・最初のメッセージ対応
    if user_text in ["ヘルプ", "help", "?", "？"]:
        await reply(line_api, event.reply_token, _help_text())
        return

    try:
        fortune_text, character_name = await call_voifor_text_fortune(question)
        reply_text = f"🔮 {character_name} の見立て\n\n{fortune_text}\n\n──────\n💬 もう一度占ってほしいなら、何かメッセージを送ってください\n📱 もっと本格的に：VOIFORアプリ（公開準備中）"
    except Exception as e:
        logging.exception("Fortune API failed")
        reply_text = f"占いの神秘との接続に失敗したわ…少し時間を置いてもう一度試してみて 🌙\n\n（{type(e).__name__}）"

    await reply(line_api, event.reply_token, reply_text)


async def call_voifor_text_fortune(user_text: str):
    """VOIFOR の /text-fortune を呼び出し、占い文字列とキャラ名を返す"""
    character = random.choice(CHARACTERS)

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

    return data.get("fortune", "（結果が読み取れませんでした）"), character["name"]


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
        "何かメッセージを送ると、AI占い師がランダムに選ばれて占ってくれます。\n\n"
        "【使い方の例】\n"
        "・「占って」\n"
        "・「最近恋愛うまくいかない」\n"
        "・「仕事のことで悩んでる」\n"
        "・「今日の運勢」\n\n"
        "【占い師（ランダム）】\n"
        "・🦂 鬼術師（容赦ない）\n"
        "・👼 エンジェル♀（優しい）\n"
        "・🐱 クロネコ（ツンデレ）\n\n"
        "📱 もっと本格的な占いはアプリ版で（リリース予定）"
    )
