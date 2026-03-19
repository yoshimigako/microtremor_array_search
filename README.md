# microtremor_array_search

OpenStreetMap を用いて、微動アレイ観測の 3 点観測点配置を自動設計する Python スクリプト群です。

## 管理対象

このリポジトリでは、原則として以下のみ Git 管理します。

- `*.py`
- `*.md`

CSV、HTML、KML、キャッシュなどの生成物や作業データは Git 管理対象外です。

## 主なファイル

- `microtremor_array_search202501.py`
- `microtremor_array_search202501-v2.py`
- `microtremor_array_search202501-v3.py`
- `microtremor_array_search202501-v4.py`
- `microtremor_array_search202501-v4_inside_noisy.py`
- `microtremor_array_search202501-v4_local_crs.py`
- `HANDOFF_20260318_microtremor_array_search_v4_local_crs.md`
- `REPORT_20260318_microtremor_array_search_v4_local_crs_analysis.md`

## 実行に関する注意

- 実行確認用の想定環境は `conda activate pygmt`
- OSM 取得を行うため、実行時にはネットワーク接続が必要
- 今後の改修や検証は、このディレクトリ直下ではなく別作業ディレクトリで行う運用とする

## Git / GitHub 運用メモ

- 既存リポジトリ: `yoshimigako/microtremor_array_search`
- 既定ブランチ: `main`
- GitHub 接続は SSH を使用

秘匿情報はリポジトリに保存しません。SSH 秘密鍵、トークン、ローカル環境固有情報、認証設定の詳細値はコミット対象外です。
