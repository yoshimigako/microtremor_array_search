# ============================================================
# 微動アレイ観測点 自動設計プログラム【ctrl-param.csv対応・完成版】
# ============================================================
import os
import subprocess
import numpy as np
import pandas as pd
import osmnx as ox
import folium
from shapely.geometry import Point
from pathlib import Path
from pyproj import CRS, Transformer
import matplotlib.colors as mcolors
from matplotlib import colormaps
from osmnx._errors import InsufficientResponseError
import geopandas as gpd
import pyogrio

# ============================================================
# 入力ファイル
# ============================================================
CENTER_FILE = "centers.csv"
RADIUS_FILE = "radius.csv"
CTRL_PARAM_FILE = "ctrl-param.csv"

# ============================================================
# 内部パラメータ読み込み（#行無視）
# ============================================================
ctrl = pd.read_csv(CTRL_PARAM_FILE, comment='#', index_col=0)["value"].to_dict()

def get_float(name, default):
    return float(ctrl.get(name, default))

def get_int(name, default):
    return int(float(ctrl.get(name, default)))

# パラメータに反映
CENTER_SEARCH_RADIUS = get_float("CENTER_SEARCH_RADIUS", 200)
CENTER_GRID_STEP = get_float("CENTER_GRID_STEP", 10)
ANGLE_STEP = get_float("ANGLE_STEP", 1)
ANGLE_TOL = get_float("ANGLE_TOL", 2.5)
QUIET_DISTANCE = get_float("QUIET_DISTANCE", 30)
ROAD_TOL = get_float("ROAD_TOL", 10)
SEARCH_RADIUS = get_float("SEARCH_RADIUS", 4000)
RADIUS_TOL_RATIO = get_float("RADIUS_TOL_RATIO", 0.15)
RADIUS_REFINE_STEP = get_int("RADIUS_REFINE_STEP", 1)
MAX_CANDIDATES = get_int("MAX_CANDIDATES", 3)
OSM_SOURCE = str(ctrl.get("OSM_SOURCE", "local_pbf")).strip().lower()
OSM_PBF_FILE = str(ctrl.get("OSM_PBF_FILE", "")).strip()
LOCAL_OSM_MARGIN = get_float("LOCAL_OSM_MARGIN", 100)
LOCAL_CACHE_DIR = str(ctrl.get("LOCAL_CACHE_DIR", "local_osm_cache")).strip()
OGR2OGR_BIN = str(ctrl.get("OGR2OGR_BIN", "/opt/homebrew/bin/ogr2ogr")).strip()
DIVERSE_POOL_SIZE = get_int("DIVERSE_POOL_SIZE", 50)

print(f"CENTER_SEARCH_RADIUS: {CENTER_SEARCH_RADIUS}")
print(f"CENTER_GRID_STEP: {CENTER_GRID_STEP}")
print(f"ANGLE_STEP :{ANGLE_STEP}")
print(f"ANGLE_TOL : {ANGLE_TOL}")
print(f"QUIET_DISTANCE : {QUIET_DISTANCE}")
print(f"ROAD_TOL : {ROAD_TOL}")
print(f"SEARCH_RADIUS : {SEARCH_RADIUS}")
print(f"RADIUS_TOL_RATIO : {RADIUS_TOL_RATIO}")
print(f"RADIUS_REFINE_STEP (m: int) : {RADIUS_REFINE_STEP}")
print(f"MAX_CANDIDATES : {MAX_CANDIDATES}")
print(f"OSM_SOURCE : {OSM_SOURCE}")
print(f"OSM_PBF_FILE : {OSM_PBF_FILE}")
print(f"LOCAL_OSM_MARGIN : {LOCAL_OSM_MARGIN}")
print(f"LOCAL_CACHE_DIR : {LOCAL_CACHE_DIR}")
print(f"OGR2OGR_BIN : {OGR2OGR_BIN}")
print(f"DIVERSE_POOL_SIZE : {DIVERSE_POOL_SIZE}")

#観測点の選択ペナルティパラメータ
PENALTY_WATER = get_float("PENALTY_WATER", 1e6)
PENALTY_NOISY_SCALE = get_float("PENALTY_NOISY_SCALE", 100.0)
PENALTY_PREFER_SCALE = get_float("PENALTY_PREFER_SCALE", 10.0)

print(f"PENALTY_WATER : {PENALTY_WATER}")
print(f"PENALTY_NOISY_SCALE : {PENALTY_NOISY_SCALE}")
print(f"PENALTY_PREFER_SCALE : {PENALTY_PREFER_SCALE}")


CSV_PRIMARY = "array_primary_results.csv"
CSV_BEST = "array_best_by_radius.csv"
CSV_PENALTY = "array_penalty_breakdown.csv"
MAP_FILE = "array_design_map.html"

print(f" Output files ")
print(f"共通中心点アレイ:{CSV_PRIMARY}")
print(f"観測半径毎の最適アレイ: {CSV_BEST}")
print(f"アレイ配置図（folium使用）: {MAP_FILE}")

CENTER_ICON = {
    1: ("black", "star"),
    2: ("gray", "star"),
    3: ("lightgray", "star")
}

# ============================================================
# 探索半径読み込み
# ============================================================
df_r = pd.read_csv(RADIUS_FILE)
RADII = sorted(df_r["radius"].astype(float).tolist())

if len(RADII) >= 10:
    raise ValueError("探索半径は10未満にしてください")

print(f"✔ 探索半径読み込み: {RADII}")

if OSM_SOURCE == "local_pbf":
    if not OSM_PBF_FILE:
        raise ValueError("OSM_SOURCE=local_pbf の場合は ctrl-param.csv に OSM_PBF_FILE を指定してください")
    OSM_PBF_PATH = Path(OSM_PBF_FILE).expanduser()
    if not OSM_PBF_PATH.exists():
        raise FileNotFoundError(f"指定した OSM_PBF_FILE が見つかりません: {OSM_PBF_PATH}")
else:
    OSM_PBF_PATH = None

# ============================================================
# 半径ごとの色を自動生成
# ============================================================
cmap = colormaps["tab10"].resampled(len(RADII))
RADIUS_COLOR = {R: mcolors.to_hex(cmap(i)) for i, R in enumerate(RADII)}

# ============================================================
# 座標変換（ローカルUTM: 距離がメートルで正しく扱える）
# ============================================================
def utm_crs_from_latlon(lat, lon):
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        epsg = 32600 + zone  # WGS84 / UTM Northern
    else:
        epsg = 32700 + zone  # WGS84 / UTM Southern
    return CRS.from_epsg(epsg)

# シードの平均位置からUTMゾーンを決定
df_seed = pd.read_csv(CENTER_FILE)
mean_lat = float(df_seed["lat"].mean())
mean_lon = float(df_seed["lon"].mean())
PROJ_CRS = utm_crs_from_latlon(mean_lat, mean_lon)

print(f"✔ 投影CRS: {PROJ_CRS.to_string()}")

to_xy = Transformer.from_crs("EPSG:4326", PROJ_CRS, always_xy=True)
to_ll = Transformer.from_crs(PROJ_CRS, "EPSG:4326", always_xy=True)

# ============================================================
# seed 読み込み
# ============================================================
seeds = []
for _, r in df_seed.iterrows():
    x, y = to_xy.transform(r["lon"], r["lat"])
    seeds.append({
        "id": r["id"],
        "pt": Point(x, y),
        "lat": r["lat"],
        "lon": r["lon"]
    })

# ============================================================
# CSV 初期化
# ============================================================
pd.DataFrame(columns=[
    "seed_id", "rank", "radius",
    "center_lat", "center_lon",
    "point_id", "lat", "lon",
    "azimuth_deg", "triangle_error"
]).to_csv(CSV_PRIMARY, index=False)

pd.DataFrame(columns=[
    "seed_id", "radius",
    "lat", "lon",
    "triangle_error"
]).to_csv(CSV_BEST, index=False)

pd.DataFrame(columns=[
    "seed_id",
    "radius",
    "point_type",        # center / observation
    "point_id",          # 中心点=0, 観測点=1,2,3
    "lat",
    "lon",
    "penalty_total",
    "penalty_water",
    "penalty_noisy",
    "penalty_prefer"
]).to_csv(CSV_PENALTY, index=False)


print("✔ CSV 初期化完了")

# ============================================================
# 地図初期化
# ============================================================
m = folium.Map(location=[seeds[0]["lat"], seeds[0]["lon"]], zoom_start=13)

# # ============================================================
# # OSM データ取得
# # ============================================================
# ref = seeds[0]

# def load_osm(tags):
#     return ox.features_from_point(
#         (ref["lat"], ref["lon"]),
#         tags=tags,
#         dist=SEARCH_RADIUS
#     ).to_crs(3857)

# noisy = load_osm({"highway": ["motorway", "trunk", "primary"], "railway": True, "landuse": ["industrial"]})
# prefer = load_osm({"leisure": ["park"], "landuse": ["recreation_ground"],
#                    "highway": ["residential", "service", "unclassified", "track","path","footway","cycleway"]})
# fallback = load_osm({"highway": ["secondary"]})
# water = load_osm({"natural": ["water"], "waterway": True})

# noisy_u = noisy.geometry.union_all()
# prefer_u = prefer.geometry.union_all()
# fallback_u = fallback.geometry.union_all()
# water_u = water.geometry.union_all()

def union_or_empty(gdf):
    """
    GeoDataFrame が None または空の場合に
    空の geometry を返すための安全関数
    """
    if gdf is None or len(gdf) == 0:
        return gpd.GeoSeries([], crs=PROJ_CRS).union_all()
    return gdf.geometry.union_all()

def concat_gdfs(*gdfs):
    frames = [g for g in gdfs if g is not None and len(g) > 0]
    if not frames:
        return None
    merged = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=frames[0].crs)

def mask_tag_in(gdf, column, values):
    if gdf is None or column not in gdf.columns:
        return pd.Series(False, index=gdf.index if gdf is not None else [])
    return gdf[column].fillna("").isin(values)

def mask_tag_exists(gdf, column):
    if gdf is None or column not in gdf.columns:
        return pd.Series(False, index=gdf.index if gdf is not None else [])
    return gdf[column].notna() & (gdf[column].astype(str).str.strip() != "")

def filter_gdf(gdf, mask):
    if gdf is None or len(gdf) == 0:
        return None
    filtered = gdf.loc[mask].copy()
    if len(filtered) == 0:
        return None
    return filtered

def get_local_read_radius():
    return (
        float(CENTER_SEARCH_RADIUS)
        + float(max(RADII))
        + float(max(QUIET_DISTANCE, ROAD_TOL))
        + float(LOCAL_OSM_MARGIN)
    )

def bbox_wgs84_from_projected(seed_pt, radius_m):
    corners = [
        (seed_pt.x - radius_m, seed_pt.y - radius_m),
        (seed_pt.x - radius_m, seed_pt.y + radius_m),
        (seed_pt.x + radius_m, seed_pt.y - radius_m),
        (seed_pt.x + radius_m, seed_pt.y + radius_m),
    ]
    lonlats = [to_ll.transform(x, y) for x, y in corners]
    lons = [lon for lon, _ in lonlats]
    lats = [lat for _, lat in lonlats]
    return (min(lons), min(lats), max(lons), max(lats))

def read_local_osm_layer(layer_name, source_path):
    try:
        gdf = pyogrio.read_dataframe(source_path, layer=layer_name)
    except Exception as e:
        print(f"  local cache read error: layer={layer_name} error={e}")
        return None
    if gdf is None or len(gdf) == 0:
        print(f"  local cache layer empty: {layer_name}")
        return None
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    print(f"  local cache layer loaded: {layer_name} rows={len(gdf)}")
    return gdf.to_crs(PROJ_CRS)

def build_local_bbox_cache(seed, bbox, read_radius):
    cache_dir = Path(LOCAL_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_name = f"{seed['id']}_{int(round(read_radius))}m.gpkg"
    cache_path = cache_dir / cache_name

    if cache_path.exists():
        print(f"  local cache reuse: {cache_path}")
        return cache_path

    bbox_args = [str(v) for v in bbox]
    print(f"  local cache build start: {cache_path}")

    commands = [
        [
            OGR2OGR_BIN, "-f", "GPKG", str(cache_path), str(OSM_PBF_PATH),
            "lines", "-spat", *bbox_args
        ],
        [
            OGR2OGR_BIN, "-f", "GPKG", "-update", str(cache_path), str(OSM_PBF_PATH),
            "multipolygons", "-spat", *bbox_args
        ],
    ]

    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                "local bbox cache build failed:\n"
                f"command={' '.join(cmd)}\n"
                f"stdout={result.stdout}\n"
                f"stderr={result.stderr}"
            )

    print(f"  local cache build done: {cache_path}")
    return cache_path

def load_local_osm(seed):
    read_radius = get_local_read_radius()
    bbox = bbox_wgs84_from_projected(seed["pt"], read_radius)

    print(f"  local PBF bbox: {bbox}")

    cache_path = build_local_bbox_cache(seed, bbox, read_radius)

    lines = read_local_osm_layer("lines", cache_path)
    polygons = read_local_osm_layer("multipolygons", cache_path)

    noisy_lines = filter_gdf(
        lines,
        mask_tag_in(lines, "highway", ["motorway", "trunk", "primary"])
        | mask_tag_exists(lines, "railway")
    )

    prefer_lines = filter_gdf(
        lines,
        mask_tag_in(
            lines,
            "highway",
            ["residential", "service", "unclassified", "track", "path",
             "footway", "cycleway", "tertiary", "pedestrian"]
        )
    )
    prefer_polygons = filter_gdf(
        polygons,
        mask_tag_in(polygons, "leisure", ["park"])
        | mask_tag_in(polygons, "landuse", ["recreation_ground"])
    )

    fallback = filter_gdf(lines, mask_tag_in(lines, "highway", ["secondary"]))

    water_lines = filter_gdf(lines, mask_tag_exists(lines, "waterway"))
    water_polygons = filter_gdf(
        polygons,
        mask_tag_in(polygons, "natural", ["water"])
        | mask_tag_exists(polygons, "waterway")
    )

    noisy = noisy_lines
    prefer = concat_gdfs(prefer_lines, prefer_polygons)
    water = concat_gdfs(water_lines, water_polygons)

    print(
        "  local OSM feature counts:"
        f" noisy={0 if noisy is None else len(noisy)}"
        f" prefer={0 if prefer is None else len(prefer)}"
        f" fallback={0 if fallback is None else len(fallback)}"
        f" water={0 if water is None else len(water)}"
    )

    return noisy, prefer, fallback, water

def select_diverse_top_candidates(scored, max_candidates):
    if max_candidates <= 0 or not scored:
        return []

    pool_size = min(len(scored), max(max_candidates, DIVERSE_POOL_SIZE))
    pool = scored[:pool_size]
    selected = [pool[0]]
    used_ids = {id(pool[0])}

    while len(selected) < max_candidates:
        remaining = [item for item in pool if id(item) not in used_ids]
        if not remaining:
            remaining = [item for item in scored if id(item) not in used_ids]
        if not remaining:
            break

        best_item = None
        best_key = None
        for item in remaining:
            center = item[1]
            min_dist = min(center.distance(sel[1]) for sel in selected)
            quality = item[0]
            key = (
                min_dist,
                quality[0],
                quality[1],
            )
            if best_key is None or key > best_key:
                best_key = key
                best_item = item

        selected.append(best_item)
        used_ids.add(id(best_item))

    return selected

# ============================================================
# ★追加：グリッド周囲から中心点候補を生成する関数（最小追加）
# ============================================================
def sample_center_candidates(grid_pt, search_radius, step):
    """
    グリッド点の周囲（search_radius 内）から中心点候補を生成する
    グリッド点そのものは評価せず、その近傍から適切な点を選ぶための補助関数
    """
    candidates = []
    xs = np.arange(grid_pt.x - search_radius,
                   grid_pt.x + search_radius + step, step)
    ys = np.arange(grid_pt.y - search_radius,
                   grid_pt.y + search_radius + step, step)

    for x in xs:
        for y in ys:
            p = Point(x, y)
            if p.distance(grid_pt) <= search_radius:
                candidates.append(p)
    return candidates

# ============================================================
# ヘルパ関数（方位・中心点判定・三角形誤差・円交点）
# ============================================================
def azimuth(p, c):
    dx = p.x - c.x
    dy = p.y - c.y
    return (np.degrees(np.arctan2(dx, dy)) + 360) % 360

def is_center_ok(pt):
    if water_u.distance(pt) == 0: return False
    if noisy_u.distance(pt) < QUIET_DISTANCE: return False
    return pt.distance(prefer_u) <= ROAD_TOL

# def triangle_error(center, pts, R):
#     d_err = sum(abs(center.distance(p) - R) for p in pts)
#     angs = sorted(azimuth(p, center) for p in pts)
#     ang_err = sum(abs((angs[(i+1)%3]-angs[i])%360 - 120) for i in range(3))
#     return d_err + R*np.radians(ang_err)

def triangle_error(center, pts, R):
    # 距離誤差
    d_err = sum(abs(center.distance(p) - R) for p in pts)

    # 角度誤差
    angs = sorted(azimuth(p, center) for p in pts)
    ang_err = sum(
        abs((angs[(i+1)%3] - angs[i]) % 360 - 120)
        for i in range(3)
    )

    # 観測点の環境ペナルティ
    env_pen = sum(point_environment_penalty(p) for p in pts)

    return d_err + R * np.radians(ang_err) + env_pen

def point_environment_penalty(pt):
    """
    観測点の環境的な不適合度を数値化する
    小さいほど良い
    """
    penalty = 0.0

    # 水面は強いペナルティ（ほぼNGだが排除はしない）
    if water_u.distance(pt) == 0:
        penalty += PENALTY_WATER

    # 鉄道・幹線道路に近いほど悪い
    d_noisy = noisy_u.distance(pt)
    if d_noisy < QUIET_DISTANCE:
        penalty += (QUIET_DISTANCE - d_noisy) * PENALTY_NOISY_SCALE

    # 道路・公園から離れるほど悪い
    d_prefer = pt.distance(prefer_u)
    if d_prefer > ROAD_TOL:
        penalty += (d_prefer - ROAD_TOL) * PENALTY_PREFER_SCALE

    return penalty

def point_environment_penalty_detail(pt):
    """
    観測点 or 中心点に対する環境ペナルティの内訳を返す
    """
    pw = 0.0
    pn = 0.0
    pp = 0.0

    # 水面
    if water_u.distance(pt) == 0:
        pw = PENALTY_WATER

    # 鉄道・幹線道路
    d_noisy = noisy_u.distance(pt)
    if d_noisy < QUIET_DISTANCE:
        pn = (QUIET_DISTANCE - d_noisy) * PENALTY_NOISY_SCALE

    # 道路・公園逸脱
    d_prefer = pt.distance(prefer_u)
    if d_prefer > ROAD_TOL:
        pp = (d_prefer - ROAD_TOL) * PENALTY_PREFER_SCALE

    return {
        "total": pw + pn + pp,
        "water": pw,
        "noisy": pn,
        "prefer": pp
    }



def get_circle_intersections(center, R):
    circle = center.buffer(R).boundary
    pts = []
    for geom in [prefer_u, fallback_u]:
        inter = circle.intersection(geom)
        if inter.is_empty: continue
        if inter.geom_type == "Point": pts.append(inter)
        elif inter.geom_type == "MultiPoint": pts.extend(inter.geoms)
        elif inter.geom_type in ["LineString","MultiLineString"]:
            lines = inter.geoms if hasattr(inter,"geoms") else [inter]
            for ln in lines:
               # for f in np.linspace(0,1,5):
                for f in np.linspace(0,1,20):
                    pts.append(ln.interpolate(f, normalized=True))
    return pts

def find_array(center, R):
    pts = get_circle_intersections(center,R)
    if len(pts)<3: return None
    angs = [(p, azimuth(p, center)) for p in pts]
    best=None; best_err=1e99
    for theta in range(0,360,int(ANGLE_STEP)):
        targets=[(theta+k)%360 for k in (0,120,240)]
        sel=[]
        for t in targets:
            cand=[p for p,a in angs if abs(((a-t+180)%360)-180)<=ANGLE_TOL]
            if not cand: break
            sel.append(cand[0])
        if len(sel)==3:
            err=triangle_error(center, sel, R)
            if err<best_err:
                best_err=err
                best=(theta, sel, err)
    return best

# ============================================================
# 探索メインループ（siteごと）
# ============================================================
for seed in seeds:
    sid = seed["id"]
    base = seed["pt"]
    print(f"\n===== {sid}: 探索開始 =====")
    print(f"\n===== {sid}: OSMデータ DL開始 =====")

    # ============================================================
    # site毎にOSM データ取得
    # ============================================================
    if OSM_SOURCE == "local_pbf":
        noisy, prefer, fallback, water = load_local_osm(seed)
    else:
        def load_osm(tags):
            try:
                gdf = ox.features_from_point(
                    (seed["lat"], seed["lon"]),
                    tags=tags,
                    dist=SEARCH_RADIUS
                ).to_crs(PROJ_CRS)
                if len(gdf) == 0:
                    return None
                return gdf
            except InsufficientResponseError:
                return None

        noisy = load_osm({"highway": ["motorway", "trunk", "primary"], "railway": True})
        prefer = load_osm({"leisure": ["park"], "landuse": ["recreation_ground"],
                        "highway": ["residential", "service", "unclassified", "track","path","footway","cycleway", "tertiary", "pedestrian"]})
        fallback = load_osm({"highway": ["secondary"]})
        water = load_osm({"natural": ["water"], "waterway": True})

    if fallback is None:
        print(" ここにはsecondary道路なし")

    noisy_u    = union_or_empty(noisy)
    prefer_u   = union_or_empty(prefer)
    fallback_u = union_or_empty(fallback)
    water_u    = union_or_empty(water)

    # noisy_u = noisy.geometry.union_all()
    # prefer_u = prefer.geometry.union_all()
    # fallback_u = fallback.geometry.union_all()
    # water_u = water.geometry.union_all()

    print(f"\n===== {sid}: OSMデータ DL完了 =====")

    best_by_radius = {R: None for R in RADII}
    scored = []

    centers = []
    
    # グリッド周囲探索半径（グリッド間隔の半分）
    SEARCH_R = CENTER_GRID_STEP / 2.0
    SAMPLE_STEP = SEARCH_R / 2.0  # 細かすぎない最小サンプリング

    for dx in range(-int(CENTER_SEARCH_RADIUS),
                    int(CENTER_SEARCH_RADIUS) + 1,
                    int(CENTER_GRID_STEP)):
        for dy in range(-int(CENTER_SEARCH_RADIUS),
                        int(CENTER_SEARCH_RADIUS) + 1,
                        int(CENTER_GRID_STEP)):

            if dx*dx + dy*dy > CENTER_SEARCH_RADIUS**2:
                continue

            grid_pt = Point(base.x + dx, base.y + dy)

            # グリッド周囲から候補点を生成
            cand_pts = sample_center_candidates(
                grid_pt,
                SEARCH_R,
                SAMPLE_STEP
            )

            # is_center_ok を満たす最初の点を採用
            best_pt = None
            for p in cand_pts:
                if is_center_ok(p):
                    best_pt = p
                    break

            if best_pt is not None:
                centers.append(best_pt)

    print(f"  中心点候補数: {len(centers)}")

    for i, c0 in enumerate(centers, 1):
        print(f"    中心点評価 {i}/{len(centers)}", end="\r")
        valid={}
        for R in RADII:
            res=find_array(c0,R)
            if res:
                theta, pts, err=res
                valid.setdefault(R,[]).append((theta,pts,err))
                cur=best_by_radius[R]
                if cur is None or err<cur["error"]:
                    best_by_radius[R]={"center":c0,"pts":pts,"error":err}
        if valid: scored.append(((len(valid),max(valid)),c0,valid))

    scored.sort(reverse=True,key=lambda x:x[0])
    top=select_diverse_top_candidates(scored, MAX_CANDIDATES)

    if top:
        print("  採用中心点候補:")
        for rank, (_, c0, valid) in enumerate(top, 1):
            distances = []
            for _, other_c0, _ in top[:rank-1]:
                distances.append(c0.distance(other_c0))
            min_dist = min(distances) if distances else 0.0
            print(
                f"    rank={rank}"
                f" success_radii={len(valid)}"
                f" max_radius={max(valid)}"
                f" min_center_distance={min_dist:.1f} m"
            )

    if top:
        _, c0, valid=top[0]
        missing=[R for R in RADII if R not in valid]
        for R0 in missing:
            print(f"  再探索: 半径 {R0} m")
            max_dR = int(R0 * RADIUS_TOL_RATIO)
            step = int(RADIUS_REFINE_STEP)
            # R0 に近い半径を優先（0, +step, -step, +2step, -2step, ...）
            offsets = [0]
            k = step
            while k <= max_dR:
                offsets.append(k)
                offsets.append(-k)
                k += step
            for dR in offsets:
                R = R0 + dR
                print(f"    試行 R={R} m", end="\r")
                res=find_array(c0,R)
                if res:
                    theta, pts, err=res
                    valid.setdefault(R0,[]).append((theta,pts,err))
                    print(f"\n    ✔ 再探索成功 R0={R0} → R={R}")
                    break

    # CSV & Map
    rows_primary=[]; rows_best=[]; rows_penalty=[] 
    for rank,(_,c0,valid) in enumerate(top,1):
        lon,lat=to_ll.transform(c0.x,c0.y)
        color,icon=CENTER_ICON[rank]
        folium.Marker([lat,lon],icon=folium.Icon(color=color,icon=icon),
                      tooltip=f"{sid} cand{rank}").add_to(m)
        for R,lst in valid.items():
            theta,pts,err=lst[-1]
            color=RADIUS_COLOR[R]
            poly=[]
            rows_primary.append([sid,rank,R,lat,lon,0,lat,lon,0,0])#中心点保存
            for i,p in enumerate(pts,1):
                lo,la=to_ll.transform(p.x,p.y)
                az=azimuth(p,c0)
                rows_primary.append([sid,rank,R,lat,lon,i,la,lo,az,err])
                poly.append([la,lo])
                folium.CircleMarker([la,lo],radius=4,color=color,fill=True).add_to(m)
            poly.append(poly[0])
            folium.Polygon(poly,color=color,fill=False).add_to(m)

    for R,d in best_by_radius.items():
        if d is None: continue
        for p in d["pts"]:
            lo,la=to_ll.transform(p.x,p.y)
            rows_best.append([sid,R,la,lo,d["error"]])
        c0=d["center"]; pts=d["pts"]; err=d["error"]
        color=RADIUS_COLOR[R]
        clon,clat=to_ll.transform(c0.x,c0.y)
        rows_best.append([sid,R,clat,clon,0]) #中心点保存
        folium.CircleMarker([clat,clon],radius=5,color=color,fill=True,
                            fill_opacity=0.6,
                            tooltip=f"{sid} best-center R={R} err={err:.1f}").add_to(m)
        poly=[]
        for p in pts:
            lon,lat=to_ll.transform(p.x,p.y)
            poly.append([lat,lon])
            folium.CircleMarker([lat,lon],radius=3,color=color,fill=True,
                                fill_opacity=0.5,
                                tooltip=f"{sid} best R={R} err={err:.1f}").add_to(m)
        poly.append(poly[0])
        folium.Polygon(poly,color=color,weight=2,dash_array="5,5",
                       fill=False,tooltip=f"{sid} best-by-radius R={R} err={err:.1f}").add_to(m)

        pen = point_environment_penalty_detail(c0)

        rows_penalty.append([
            sid, R, "center", 0,
            clat, clon,
            pen["total"], pen["water"], pen["noisy"], pen["prefer"]
        ])

        for i, p in enumerate(pts, 1):
            lo, la = to_ll.transform(p.x, p.y)
            pen = point_environment_penalty_detail(p)

            rows_penalty.append([
                sid, R, "observation", i,
                la, lo,
                pen["total"], pen["water"], pen["noisy"], pen["prefer"]
            ])



    pd.DataFrame(rows_primary).to_csv(CSV_PRIMARY,mode="a",header=False,index=False)
    pd.DataFrame(rows_best).to_csv(CSV_BEST,mode="a",header=False,index=False)
    pd.DataFrame(rows_penalty).to_csv(CSV_PENALTY,mode="a", header=False, index=False)
    m.save(MAP_FILE)
    print(f"\n✔ {sid}: CSV / 地図 更新完了")

print("\n=== 全 site 探索完了 ===")
