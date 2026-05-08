# VOIFOR LINE Bot

[VOIFOR -声占い-](https://github.com/866gf67fvk-ship-it/voifor) の LINE Bot 版。
LINE で「占って」と送ると、AI 占い師が答えてくれる。

## 機能

- 「占って」「最近モヤモヤしてる」など、自由な日本語メッセージで占い起動
- キャラ指定可能：「鬼術師で」「天使で」「猫で」
- 鬼術師（容赦ない）/ エンジェル♀（優しい）/ クロネコ（ツンデレ）の3キャラ
- AI（Claude）が250〜350字程度で占い文＋キーワード＋ひとこと
- ヘルプ：「ヘルプ」と送ると使い方が出る

## アーキテクチャ

```
LINE ユーザー
   ↓ メッセージ
LINE プラットフォーム
   ↓ Webhook (POST /callback)
voifor-line-bot (Python on Vercel)  ← このリポジトリ
   ↓ /text-fortune を呼ぶ
voifor-t5qi.vercel.app (Node.js on Vercel)
   ↓ Claude API
ユーザーに占い結果が返る
```

## 技術スタック

- Python 3.8+ / FastAPI
- line-bot-sdk-python v3
- httpx（非同期 HTTP クライアント）
- Vercel Python serverless

## 環境変数

| Key | 値 |
|---|---|
| `LINE_CHANNEL_SECRET` | LINE Developers の Channel secret |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Developers の Channel access token (long-lived) |
| `VOIFOR_API_BASE` | VOIFOR APIのURL（既定: `https://voifor-t5qi.vercel.app`） |

## デプロイ

1. このリポジトリを Vercel に Import
2. 上記の環境変数を設定
3. Deploy
4. デプロイURLの末尾 `/callback` を、LINE Developers の Webhook URL に設定

## ローカル開発

```bash
pip install -r requirements.txt
cp .env.example .env  # 値を入れる
uvicorn main:app --reload
```

別ターミナルで ngrok 等を立ててLINE 側に Webhook URL 通知。

## ライセンス

個人開発・実験用途。商用利用については相談を。

## 開発者

[@866gf67fvk-ship-it](https://github.com/866gf67fvk-ship-it)
