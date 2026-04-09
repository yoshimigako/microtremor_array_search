# 引き継ぎメモ: microtremor_array_search202501-v4_local_crs.py

作成日: 2026-03-18
対象: `microtremor_array_search202501-v4_local_crs.py`

運用メモ追記:

- 実行確認用の環境は `conda activate pygmt`
- 今後の改修・検証作業はこのディレクトリ直下ではなく、別ディレクトリで行う
- Git 管理は開始済み。原則として `*.py` と `*.md` のみを追跡する
- GitHub リポジトリは作成済みで、既定ブランチは `main`
- 認証情報、秘密鍵、トークン、公開鍵本文などの秘匿情報は文書・コード・コミットに残さない
- Git 管理側の現行版にも GeoFabrik ローカル PBF 読み込み実装を取り込んだ

## 1. このスクリプトの役割

このスクリプトは OpenStreetMap を用いて、微動アレイ観測のための 3 点観測点を自動設計する。

- 入力:
  - `centers.csv`: シード中心点候補
  - `radius.csv`: 設計したい観測半径一覧
  - `ctrl-param.csv`: 探索半径、角度許容、静穏距離、ペナルティ重みなど
- 出力:
  - `array_primary_results.csv`: 上位中心候補ごとのアレイ結果
  - `array_best_by_radius.csv`: 各半径で最良と判定されたアレイ
  - `array_penalty_breakdown.csv`: 中心点/観測点ごとの環境ペナルティ内訳
  - `array_design_map.html`: Folium 地図

## 2. v4 から v4_local_crs への主要変更

`microtremor_array_search202501-v4.py` との差分を確認済み。主要な変更は投影座標系のみ。

- 旧版は `EPSG:3857` を使用
- 本版はシード群の平均緯度経度から UTM ゾーンを決め、`PROJ_CRS` を生成
- 距離評価、バッファ半径、交点探索、OSM データ投影はすべて `PROJ_CRS` 上で処理

この変更により、メートル単位の距離が Web Mercator より自然に扱われる。

## 3. 処理フロー要約

1. `ctrl-param.csv` を読み込み、探索条件とペナルティ重みを設定
2. `radius.csv` から探索半径リストを読み込む
3. `centers.csv` からシード点を読み込み、WGS84 からローカル UTM に変換
4. 出力 CSV を毎回初期化
5. シードごとに OSM データを取得
6. シード周辺に中心点候補グリッドを生成
7. 各グリッド点の周囲から「中心点として成立する点」を探す
8. 各中心点候補に対し、各半径で正三角形に近い 3 点配置を探索
9. 上位候補を `array_primary_results.csv` に保存
10. 半径別ベストを `array_best_by_radius.csv` と `array_penalty_breakdown.csv` に保存
11. 地図を `array_design_map.html` に保存

## 4. OSM の使い方

現行版は `ctrl-param.csv` の `OSM_SOURCE` で OSM 入力方式を切り替える。

- `OSM_SOURCE=local_pbf`: GeoFabrik 等の `.osm.pbf` をローカル読込
- `OSM_SOURCE=overpass`: 従来の `ox.features_from_point(..., dist=SEARCH_RADIUS)`

`local_pbf` では、seed 周辺 bbox を一度だけ `ogr2ogr` で `local_osm_cache/*.gpkg` に切り出し、その `lines` / `multipolygons` レイヤを `pyogrio` で読む。

そこから以下を組み立てる。

- `noisy`: `motorway`, `trunk`, `primary`, `railway`
- `prefer`: `park`, `recreation_ground`, `residential`, `service`, `unclassified`, `track`, `path`, `footway`, `cycleway`, `tertiary`, `pedestrian`
- `fallback`: `secondary`
- `water`: `natural=water`, `waterway`

各 GeoDataFrame は `union_or_empty` で単一ジオメトリにまとめられる。既定運用は `local_pbf`。

## 5. 中心点候補の作り方

中心点候補はシードの周囲 `CENTER_SEARCH_RADIUS` m の円内で、`CENTER_GRID_STEP` m 間隔のグリッドを張って作る。

各グリッド点に対し:

- 半径 `CENTER_GRID_STEP / 2` の近傍を再サンプリング
- `is_center_ok()` を満たす最初の点をそのグリッドの代表点として採用

`is_center_ok()` の条件は以下。

- 水面上ではない
- 幹線道路/鉄道から `QUIET_DISTANCE` m 以上離れる
- `prefer` から `ROAD_TOL` m 以内

## 6. 観測点探索ロジック

観測点探索は `find_array(center, R)` が担当する。

- 中心点半径 `R` の円周を作る
- 円周と `prefer_u`, `fallback_u` の交点を候補観測点にする
- 交点が線分になる場合は 20 点に補間して候補化する
- 角度 `theta = 0..359` を `ANGLE_STEP` 刻みで走査
- 目標角 `theta`, `theta+120`, `theta+240` の各方向について、`ANGLE_TOL` 以内の最初の候補点を採用
- 3 点そろった場合に `triangle_error()` で評価し、最小誤差を採用

## 7. 誤差関数

`triangle_error(center, pts, R)` は以下の和。

- 半径誤差: `sum(abs(distance(center, p) - R))`
- 角度誤差: 3 点の方位差が 120 度からどれだけずれるか
- 環境ペナルティ: 各観測点に対する `point_environment_penalty()`

環境ペナルティは以下。

- 水面上: `PENALTY_WATER`
- noisy 近接: `(QUIET_DISTANCE - d_noisy) * PENALTY_NOISY_SCALE`
- prefer からの逸脱: `(d_prefer - ROAD_TOL) * PENALTY_PREFER_SCALE`

## 8. 出力仕様

### `array_primary_results.csv`

- 上位 `MAX_CANDIDATES` 個の中心候補について保存
- `point_id=0` が中心点
- `point_id=1..3` が観測点
- `triangle_error` は観測点 3 点に共通値

### `array_best_by_radius.csv`

- 半径ごとに最小誤差だった 1 アレイを保存
- 観測点 3 行 + 中心点 1 行
- 中心点行の `triangle_error` は `0`

### `array_penalty_breakdown.csv`

- 半径ごとのベストアレイについて保存
- 中心点 1 行 + 観測点 3 行
- `penalty_total`, `penalty_water`, `penalty_noisy`, `penalty_prefer` を記録

## 9. 現時点で確認できた実データ傾向

作業ディレクトリの出力 CSV を目視した範囲では、現在の `MYZ` ケースでは:

- `array_primary_results.csv` に半径 200, 250, 400, 500, 700, 1000, 1200 m の結果あり
- `array_best_by_radius.csv` は各半径ごとに 4 行構成
- `array_penalty_breakdown.csv` の先頭部分はすべて 0 ペナルティ

つまり、現在の結果例では「候補点が prefer 上または近傍にあり、noisy や water に抵触していない」配置が得られている可能性が高い。

## 10. 実装上の注意点

重要な癖や改善候補を以下に残す。

- `scored` の順位付けは誤差最小ではなく、`(成立半径数, 成立した最大半径)` を優先する
- `array_primary_results.csv` に載る上位中心候補と、`array_best_by_radius.csv` の半径別ベストは選定基準が異なる
- 再探索は `top[0]` のみ対象で、`best_by_radius` を更新しない
- `find_array()` は各目標角で最初の候補点だけを使うため、角度帯内の他候補を比較しない
- `sample_center_candidates()` も `is_center_ok()` を満たした最初の点を採用するため、最良点探索ではなく「最初に見つかった可用点」探索
- `CENTER_ICON` は 1,2,3 しか定義していないため、`MAX_CANDIDATES > 3` だと地図出力で落ちる
- `os` は import されているが未使用
- `local_pbf` では `pyogrio` と `ogr2ogr` が追加で必要
- `overpass` を使う場合のみネットワークが必要

## 11. 追加作業の推奨順

次に手を入れるなら以下の順が妥当。

1. `best_by_radius` と再探索の整合を取る
2. `find_array()` で角度帯内の複数候補を比較する
3. 中心点候補の選び方を「最初の可用点」から「最小ペナルティ点」に変更する
4. `MAX_CANDIDATES > 3` 対応を入れる
5. 実行環境を整えて再現実行し、代表地点でログと出力を検証する

## 12. 追加実装メモ

- `OSM_SOURCE`, `OSM_PBF_FILE`, `LOCAL_OSM_MARGIN`, `LOCAL_CACHE_DIR`, `OGR2OGR_BIN` を追加
- `local_pbf` ではローカル `.osm.pbf` から bbox 切り出し済み GeoPackage を再利用する
- `overpass` モードは後方互換のため残してある
- `select_diverse_top_candidates()` を追加し、上位候補の空間分散を持たせた

## 13. 今回の解析作業でできたこと / できていないこと

できたこと:

- 対象スクリプトの全体読解
- 旧版との差分把握
- 入出力ファイルの対応確認
- 既存出力 CSV の先頭確認
- Git 管理側へローカル PBF 対応版を取り込み

できていないこと:

- OSM 通信を伴う再計算
- 依存ライブラリ不足環境での動作検証

実行不能理由:

- この作業環境の `python3` に `pandas` などが未導入
- `overpass` モードの再確認は未実施

追記:

- ユーザーから、実行確認は `conda activate pygmt` 環境で可能との指示あり
- 次回以降の変更作業は別ディレクトリに作業コピーを切って進める前提とする
- 2026-03-19 時点で Git / GitHub 管理を開始済み
- `.gitignore` は `*.py` と `*.md` を除く作業生成物を追跡対象外とする方針
- GitHub 連携は SSH で通る状態まで確認済み
- 引き継ぎ文書には公開して問題ない運用情報のみ記載し、鍵や認証文字列は記録しない

## 14. 2026-04-09 追記: 本体側の既定設定と実行確認

本体ディレクトリ側の `ctrl-param.csv` を、`local_pbf` を既定とする設定へ更新した。

反映内容:

- `OSM_SOURCE=local_pbf`
- `OSM_PBF_FILE=/Users/yoshimi/work/bido/python/Geofabrik_data/japan-260317.osm.pbf`
- `LOCAL_OSM_MARGIN=100`
- `LOCAL_CACHE_DIR=local_osm_cache`
- `OGR2OGR_BIN=/opt/homebrew/bin/ogr2ogr`
- `DIVERSE_POOL_SIZE=50`
- `MAX_CANDIDATES=3`

この設定で本体側 `microtremor_array_search202501-v4_local_crs.py` を `pygmt` 環境から実行し、正常終了を確認した。

確認結果:

- 初回実行で `local_osm_cache/MYZ_1740m.gpkg` を生成
- `lines=2368`, `multipolygons=1881`
- `noisy=39`, `prefer=2181`, `fallback=2`, `water=152`
- `中心点候補数=2913`
- `array_primary_results.csv`: 65 行
- `array_best_by_radius.csv`: 29 行
- `array_penalty_breakdown.csv`: 29 行

採用候補ログ:

- rank 1: `success_radii=6`, `max_radius=1000.0`
- rank 2: `success_radii=4`, `max_radius=1200.0`, rank1 から約 `685.0 m`
- rank 3: `success_radii=5`, `max_radius=1000.0`, 最小距離約 `400.2 m`

再探索ログ:

- rank 1 の不足半径 `1200.0 m` に対し、`1153.0 m` で代替成功

運用上の意味:

- 本体ディレクトリでも `local_pbf` 既定のまま再現実行できる状態になった
- 初回は `ogr2ogr` による bbox キャッシュ生成で重いが、次回以降は `local_osm_cache/*.gpkg` を再利用できる
