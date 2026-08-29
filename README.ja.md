# lov-ktv

[简体中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | [粵語](README.yue.md)

家庭や個室向けのセルフホスト型カラオケシステムです。スマートフォンから曲を検索・予約し、サーバーが音源の取得、歌詞の取得、ボーカル分離を自動で行い、テレビまたはブラウザーで同期歌詞とともに再生します。

[デモ](https://ktv.lovbrowser.com) · [テレビ画面](https://ktv.lovbrowser.com/tv.html) · [スマートフォンリモコン](https://ktv.lovbrowser.com/m.html)

## 特長

- **検索から始める曲ライブラリー**：ローカルファイルを事前に用意せず、曲名から検索できます。ファイルアップロードは予備手段として利用できます。
- **自動処理**：タイムスタンプ付き公式 LRC を優先的に取得し、ONNX Runtime でボーカルと伴奏を分離します。Torch や openai-whisper は不要です。
- **複数端末で操作**：テレビに表示されたルーム QR コードを読み取り、スマートフォンから検索、予約、優先順位変更、スキップ、再生操作ができます。
- **複数の再生環境**：ブラウザー版テレビ画面、Android TV ホスト、Android スマートフォンアプリに対応します。
- **オフラインキャッシュ**：Android TV は処理済みの曲を保存するため、処理サーバーが一時的に停止しても再生できます。
- **柔軟な保存先**：標準では SQLite とローカルメディアを使用し、PostgreSQL と Alibaba Cloud OSS も設定できます。

## 仕組み

```text
スマートフォン  ── 検索・予約・操作 ──▶  lov-ktv 処理サーバー
       │                                     │
       │                                     ├─ 音源と LRC の取得
       │                                     ├─ ONNX ボーカル分離
       │                                     └─ 完成データと歌詞の保存
       │                                                    │
       └──────── QR コードで入室 ───────────▶  テレビ / ブラウザー
```

音源は NetEase の試聴、SoundCloud、YouTube の順に検索します。公式 LRC を優先するため、音声認識サービスがなくてもカラオケを利用できます。

## クイックスタート

### Docker Compose（推奨）

Docker と Docker Compose が必要です。

```bash
git clone https://github.com/jingx8885/lov-ktv.git
cd lov-ktv
cp .env.example .env
docker compose up -d --build
```

起動後、次の URL を開きます。

- テレビ画面：<http://localhost:8787/tv.html>
- スマートフォン画面：<http://localhost:8787/m.html>
- サービス状態：<http://localhost:8787/api/host>

LAN 内のテレビやスマートフォンから接続する場合は、`localhost` を lov-ktv が動作する PC または NAS のアドレスに置き換えてください。`/api/host` が返す `models.separator` は `true` になります。

### Python でローカル起動

Python 3.11 以降が必要です。音源取得の全フォールバックを利用するには FFmpeg と yt-dlp も必要です。

```bash
python -m venv .venv
# Linux / macOS
.venv/bin/pip install -e backend
PYTHONPATH=backend .venv/bin/uvicorn lovktv.main:app --host 0.0.0.0 --port 8787
```

Windows PowerShell では `.venv\Scripts\python -m pip install -e backend` を実行し、`PYTHONPATH=backend` を設定してから Uvicorn を起動してください。

## Android アプリ

- [Android TV](android-tv/README.md)：LAN ホスト、処理済み曲のキャッシュ、スマートフォンから送られる低遅延 UDP マイク音声の受信に対応します。
- [Android スマートフォン](android-phone/README.md)：曲の予約と再生操作、およびテレビへの低遅延マイク音声送信に対応します。

スマートフォン向け Web 画面でも曲を予約できますが、低遅延マイク機能には Android の両アプリが必要です。

## 設定

`.env.example` を `.env` にコピーし、必要な項目だけを設定してください。データベースを設定しない場合は `data/lovktv.sqlite`、オブジェクトストレージを設定しない場合は `data/media` を使用します。

| 環境変数 | 用途 |
| --- | --- |
| `LOVKTV_PUBLIC_URL` | 公開 URL と OAuth コールバックの基点 |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | WeChat Open Platform ログイン |
| `WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET` | WeChat 公式アカウント内ログイン |
| `LOVKTV_DATABASE_URL` | PostgreSQL 接続文字列 |
| `ALIYUN_OSS_*` | 処理済みメディア用 Alibaba Cloud OSS |
| `LOVKTV_HTTPS_PROXY` | NetEase 試聴 / yt-dlp ダウンロードだけに使う HTTPS プロキシ |

`.env`、秘密情報、`data/`、曲ライブラリー、ビルド済み APK をコミットしないでください。

## ドキュメント

- [製品仕様](docs/SPEC.md)
- [Epic / Issue グラフ](docs/GRAPH.md)
- [API リファレンス](docs/api.md)
- [データモデル](docs/schema.md)

## 著作権とライセンス

本プロジェクトのオリジナルコードは [Apache License 2.0](LICENSE) で提供されます。

サードパーティー依存関係、参考プロジェクト、および `vendor/` 内のコンテンツには、それぞれのライセンスが適用されます。lovjpn は PolyForm Noncommercial ライセンスです。楽曲、歌詞、カバー画像、動画の権利は各権利者に帰属します。利用者は、地域の法律およびコンテンツプラットフォームの規約に従って導入・利用する責任があります。許諾のないメディアを公開配布しないでください。
