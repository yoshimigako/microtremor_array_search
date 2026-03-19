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

## 実行環境

このプロジェクトは特定の環境名に依存しません。ローカルでは `pygmt` という名前の conda 環境で確認されていますが、必要なのは環境名ではなく以下の実行条件です。

- Python 3.9 系
- `numpy`
- `pandas`
- `osmnx`
- `folium`
- `shapely`
- `pyproj`
- `matplotlib`
- `geopandas`
- `pyogrio`
- GDAL / OGR (`ogr2ogr` が使えること)

ローカル確認時の主なバージョン:

- Python 3.9.18
- `numpy` 1.26.4
- `pandas` 2.2.1
- `osmnx` 2.0.7
- `folium` 0.20.0
- `shapely` 2.0.7
- `pyproj` 3.6.1
- `matplotlib` 3.8.3
- `geopandas` 1.0.1
- `pyogrio` 0.11.1

補足:

- 環境名 `pygmt` はこの Mac 上のローカル命名であり、一般的な必須条件ではありません
- スクリプト自体は `pygmt` パッケージを直接 import していません
- 現行の主運用は GeoFabrik などから取得したローカル `.osm.pbf` を使う `local_pbf` モードです
- ローカル PBF から seed 周辺 bbox を `local_osm_cache/*.gpkg` に切り出して再利用します
- `overpass` モードも残っていますが、既定運用はローカル PBF です
- 今後の改修や検証は、このディレクトリ直下ではなく別作業ディレクトリで行う運用とする

## OSM 入力

`ctrl-param.csv` で OSM 入力方式を切り替えます。

- `OSM_SOURCE=local_pbf`
- `OSM_PBF_FILE=/path/to/japan-latest.osm.pbf`
- `LOCAL_OSM_MARGIN=...`
- `LOCAL_CACHE_DIR=local_osm_cache`
- `OGR2OGR_BIN=/path/to/ogr2ogr`

`local_pbf` では `lines` と `multipolygons` を読み込み、タグ分類で `noisy / prefer / fallback / water` を構成します。

## Git / GitHub 運用メモ

- 既存リポジトリ: `yoshimigako/microtremor_array_search`
- 既定ブランチ: `main`
- GitHub 接続は SSH を使用

秘匿情報はリポジトリに保存しません。SSH 秘密鍵、トークン、ローカル環境固有情報、認証設定の詳細値はコミット対象外です。
