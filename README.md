# shorts-media

AI運用チーム（トレンド分析 → 動画制作 → 投稿 → 分析）用の動画置き場と制作ツール。

- `scripts/render_short.py` — 無料の縦型テロップ動画レンダラー（1080x1920 / 30fps / BGM付き）
  - 使い方: `python3 scripts/render_short.py specs/YYYY-MM-DD.json videos/YYYY-MM-DD.mp4`
- `specs/` — 毎日の動画の台本（JSON）
- `videos/` — 公開用の完成動画（Metricoolがraw URLから取得）
- `team.json` — 各エキスパート共通の設定
