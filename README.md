# VOIFOR LINE Bot

LINEで「占って」と送ると、VOIFOR API（Vercel）を呼び出して占い結果を返す Bot。

## アーキテクチャ

```
LINE ユーザー
   ↓ メッセージ
LINE プラットフォーム
   ↓ Webhook
voifor-line-bot (Python on Vercel)  ← このリポジトリ
   ↓ /text-fortune を呼ぶ
voifor-t5qi.vercel.app (Node.js on Vercel)
   ↓ Claude API
ユーザーに占い結果が返る
```

## 環境変数

| 変数 | 値 |
|---|---|
| `LINE_CHANNEL_SECRET` | LINE Developers の Channel secret |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Developers の Channel access token (long-lived) |
| `VOIFOR_API_BASE` | VOIFOR APIのURL（既定: `https://voifor-t5qi.vercel.app`） |

## デプロイ

1. このリポジトリを GitHub に push
2. Vercel で新規 Project として import
3. 上記の環境変数を設定
4. Deploy
5. デプロイURLの末尾に `/callback` を付けて、LINE Developers の Webhook URL に設定

## ローカル開発

```bash
pip install -r requirements.txt
cp .env.example .env  # 値を入れる
uvicorn main:app --reload
```
