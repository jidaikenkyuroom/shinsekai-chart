"""
CSVデータからindex.htmlを生成するスクリプト。
template.html の {{AUTO_DATA}} と {{LAST_DATE}} を差し替える。
"""
import csv
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "chart_config.json"
TEMPLATE_PATH = BASE_DIR / "template.html"
OUTPUT_PATH = BASE_DIR / "index.html"

CLASS_ORDER_JS = "const CLASS_ORDER = {A:0,B:1,C:2,D:3,F:4};"
PALETTE_JS = "const palette = ['#ff5c35','#4ec87a','#c8b8ff','#f0c040','#60c8e0','#e080c0','#80d060','#a0a8ff','#f09878','#98e0b0','#d8c0ff','#f8e080'];"


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def format_val(v, as_float=True):
    v = v.strip()
    if v == "" or v.lower() == "null":
        return "null"
    try:
        if as_float:
            f = float(v)
            # 小数点以下がない場合は整数表記を維持（元CSVの形式を保持）
            return v if "." in v else str(int(f))
        else:
            return str(int(float(v)))
    except ValueError:
        return "null"


def normalize_name(s):
    """ノーブレークスペース等を通常スペースに統一してstrip"""
    return s.replace(' ', ' ').strip()


def build_play_js(rows):
    header = rows[0]
    dates = header[2:]
    dates_js = "const PLAY_DATES = [" + ",".join(f'"{d}"' for d in dates) + "];"

    entries = []
    for row in rows[1:]:
        name, code = normalize_name(row[0]), row[1].strip()
        vals = ",".join(format_val(v, as_float=True) for v in row[2:])
        entries.append(f'["{name}","{code}",{vals}]')

    raw_lines = ["const rawPlay = ["]
    for i in range(0, len(entries), 2):
        chunk = entries[i : i + 2]
        raw_lines.append(",".join(chunk) + ",")
    raw_lines.append("];")

    return dates, dates_js, "\n".join(raw_lines)


def build_vote_js(rows):
    header = rows[0]
    dates = header[2:]
    dates_js = "const VOTE_DATES = [" + ",".join(f'"{d}"' for d in dates) + "];"

    entries = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        name, code = normalize_name(row[0]), row[1].strip()
        vals = ",".join(format_rank(v) for v in row[2:])
        entries.append(f'["{name}","{code}",{vals}]')

    raw_lines = ["const rawVote = ["]
    for i in range(0, len(entries), 3):
        chunk = entries[i : i + 3]
        raw_lines.append(",".join(chunk) + ",")
    raw_lines.append("];")

    return dates_js, "\n".join(raw_lines)


def build_level_broadcast_js(rows):
    level_entries = []
    broadcast_entries = []
    for row in rows[1:]:
        if len(row) < 4:
            continue
        name = normalize_name(row[0])
        level = row[2].strip()
        group = row[3].strip()
        level_entries.append(f'"{name}":"{level}"')
        broadcast_entries.append(f'"{name}":"{group}"')

    def format_map(entries, comment, varname):
        lines = [f"// {comment}", f"const {varname} = {{"]
        for i in range(0, len(entries), 4):
            chunk = entries[i : i + 4]
            lines.append(",".join(chunk) + ",")
        lines.append("};")
        return "\n".join(lines)

    level_js = format_map(
        level_entries,
        "レベル分けテスト前後半（CSVの「レベル分け」列）",
        "levelMap",
    )
    broadcast_js = format_map(
        broadcast_entries,
        "グループバトル前後半（CSVの「グループ」列）",
        "broadcastMap",
    )
    return level_js, broadcast_js


def format_rank(v):
    v = str(v).strip()
    if v == "" or v.lower() == "null":
        return "null"
    if v in ("ー", "－", "-"):
        return "-1"
    try:
        return str(int(float(v)))
    except ValueError:
        return "null"


def int_or_null(s):
    s = str(s).strip()
    if s == "" or s.lower() == "null":
        return "null"
    try:
        return str(int(float(s)))
    except ValueError:
        return "null"


def build_rank_events_js(source_dir, csv_name):
    rows = read_csv(source_dir / csv_name)
    header = rows[0]

    # 「第N回_順位」列を探してイベントキーを収集（順序保持）
    event_keys = []
    for col in header:
        if col.endswith("_順位"):
            event_keys.append(col[:-3])  # "_順位" を除いたプレフィックス

    # 各イベントの列インデックスを取得
    def col_idx(name):
        return header.index(name) if name in header else None

    event_col_map = {}
    for k in event_keys:
        event_col_map[k] = {
            "rank":    col_idx(f"{k}_順位"),
            "grRank":  col_idx(f"{k}_GR枠"),
            "natPt":   col_idx(f"{k}_国民pt"),
            "sekaiPt": col_idx(f"{k}_SEKAIpt"),
            "totalPt": col_idx(f"{k}_総票"),
        }

    def get(row, idx):
        return int_or_null(row[idx]) if idx is not None and idx < len(row) else "null"

    event_data = {}
    for k, cols in event_col_map.items():
        entries = []
        for row in rows[1:]:
            if len(row) < 2 or not row[1]:
                continue
            reading = row[1]
            vals = [get(row, cols["rank"]), get(row, cols["grRank"]),
                    get(row, cols["natPt"]), get(row, cols["sekaiPt"]), get(row, cols["totalPt"])]
            entries.append(f'["{reading}",{",".join(vals)}]')
        event_data[k] = entries

    keys_js  = "const RANK_EVENT_KEYS = [" + ",".join(f'"{k}"' for k in event_keys) + "];"
    parts    = [f'"{k}":[{",".join(v)}]' for k, v in event_data.items()]
    data_js  = "const rawRankData = {" + ",".join(parts) + "};"
    compat   = "const rawRank1 = rawRankData['第1回'] || [];"
    return "\n".join([keys_js, data_js, compat])


def build_level_js(source_dir, csv_name):
    rows = read_csv(source_dir / csv_name)
    entries = []
    for row in rows[1:]:
        row = [c.strip() for c in row]
        if len(row) < 7 or not row[1]:
            continue
        reading, first_cls, eval_cls, team, song, broadcast = row[1], row[2], row[3], row[4], row[5], row[6]
        team_esc = team.replace('"', '\\"')
        song_esc = song.replace('"', '\\"')
        entries.append(f'"{reading}":{{"cls":"{first_cls}","evalCls":"{eval_cls}","team":"{team_esc}","song":"{song_esc}","bc":"{broadcast}"}}')
    return "const rawLevelData = {" + ",".join(entries) + "};"


def build_group_battle_profile_js(source_dir, csv_name):
    rows = read_csv(source_dir / csv_name)
    entries = []
    for row in rows[1:]:
        row = [c.strip() for c in row]
        if len(row) < 7 or not row[1]:
            continue
        reading, artist, song, team, broadcast, result = row[1], row[2], row[3], row[4], row[5], row[6]
        song_esc = song.replace('"', '\\"')
        entries.append(f'"{reading}":{{"artist":"{artist}","song":"{song_esc}","team":{team},"bc":"{broadcast}","result":"{result}"}}')
    return "const rawGroupBattleData = {" + ",".join(entries) + "};"


def build_pos_oshi_js(source_dir, pos_cfg):
    rows = read_csv(source_dir / pos_cfg["oshi_cam"])
    header = rows[0]
    dates = [h.replace("_再生数", "") for h in header[3:]]

    entries = []
    for row in rows[1:]:
        if len(row) < 4:
            continue
        reading = row[1]
        vid = row[2]
        views = [int_or_null(row[3 + i]) if 3 + i < len(row) else "null" for i in range(len(dates))]
        entries.append(f'"{reading}":["{vid}",{",".join(views)}]')

    dates_js = "const POS_OSHI_DATES = [" + ",".join(f'"{d}"' for d in dates) + "];"
    data_js = "const rawPosOshi = {" + ",".join(entries) + "};"
    return dates_js + "\n" + data_js


def build_pos_js(source_dir, pos_cfg):
    team_rows = read_csv(source_dir / pos_cfg["team"])
    yt_rows = read_csv(source_dir / pos_cfg["yt_highlight"])

    team_entries = []
    for row in team_rows[1:]:
        if len(row) < 5:
            continue
        name, reading, song_artist, position, broadcast = row[0], row[1], row[2], row[3], row[4]
        parts = song_artist.split(" / ", 1)
        song = parts[0]
        artist = parts[1] if len(parts) > 1 else ""
        indiv_votes = row[5] if len(row) > 5 else ""
        team_rank   = row[6] if len(row) > 6 else ""
        benefit     = row[7] if len(row) > 7 else ""
        total_votes = row[8] if len(row) > 8 else ""
        pos_rank    = row[9] if len(row) > 9 else ""
        team_entries.append(f'["{name}","{reading}","{song}","{artist}","{position}","{broadcast}","{indiv_votes}","{team_rank}","{benefit}","{total_votes}","{pos_rank}"]')

    yt_entries = []
    for row in yt_rows[1:]:
        if len(row) < 3:
            continue
        artist, song, vid = row[0], row[1], row[2] if len(row) > 2 else ""
        yt_entries.append(f'["{artist}","{song}","{vid}"]')

    raw_team = "const rawPosBattle = [\n" + ",\n".join(team_entries) + "\n];"
    raw_yt = "const rawPosYt = [" + ",".join(yt_entries) + "];"
    return raw_team + "\n" + raw_yt


def build_battle_snap_js(source_dir, battle_cfg):
    ytoshi = read_csv(source_dir / battle_cfg["yt_oshicam"])
    header = ytoshi[0]
    view_idx = [i for i, h in enumerate(header) if h.endswith("_再生数")]
    latest_idx = view_idx[-1] if view_idx else len(header) - 1
    latest_label = header[latest_idx].replace("_再生数", "")
    oshi_entries = []
    for row in ytoshi[1:]:
        if len(row) < 2:
            continue
        reading = row[0].strip()
        lv = int_or_null(row[latest_idx]) if latest_idx < len(row) else "null"
        oshi_entries.append(f'"{reading}":[{lv}]')
    raw_oshi = (
        f"// 推しカメラ再生数（YouTube {latest_label}）: reading → [views]\n"
        f'const rawOshiCam = {{{",".join(oshi_entries)}}};'
    )

    yt = read_csv(source_dir / battle_cfg["yt_team"])
    latest_yt_label = yt[0][-1].replace("_再生数", "")
    yt_entries = []
    for row in yt[1:]:
        if len(row) < 5:
            continue
        artist, song, team, vid = row[0], row[1], row[2], row[3]
        lv = int_or_null(row[-1])
        yt_entries.append(f'["{artist}","{song}",{int(team)},"{vid}",{lv}]')
    raw_yt = (
        f"// YouTube チーム動画（全8曲）: [artist, song, team, videoId, views_{latest_yt_label}]\n"
        f'const rawYtTeam = [{",".join(yt_entries)}];'
    )

    return raw_oshi + "\n\n" + raw_yt


def build_battle_dates_js(source_dir, battle_cfg):
    ytoshi = read_csv(source_dir / battle_cfg["yt_oshicam"])
    push_dates = [ytoshi[0][i].replace("_再生数", "") for i in range(len(ytoshi[0])) if ytoshi[0][i].endswith("_再生数")]

    yt = read_csv(source_dir / battle_cfg["yt_team"])
    yt_dates = [c.replace("_再生数", "") for c in yt[0][4:]]

    full = read_csv(source_dir / battle_cfg["yt_full"])
    full_dates = [c.replace("_再生数", "") for c in full[0][4:]]

    nocut = read_csv(source_dir / battle_cfg["yt_nocut"])
    nocut_dates = [c.replace("_再生数", "") for c in nocut[0][4:]]

    def arr(lst):
        return "[" + ",".join(f'"{d}"' for d in lst) + "]"

    return "\n".join([
        f"const PUSH_CAM_DATES = {arr(push_dates)};",
        f"const YT_TEAM_DATES  = {arr(yt_dates)};",
        f"const FULL_DATES     = {arr(full_dates)};",
        f"const NOCUT_DATES    = {arr(nocut_dates)};",
    ])


def build_battle_series_js(source_dir, battle_cfg):
    ytoshi = read_csv(source_dir / battle_cfg["yt_oshicam"])
    view_indices = [i for i, h in enumerate(ytoshi[0]) if h.endswith("_再生数")]
    push_entries = []
    for row in ytoshi[1:]:
        if len(row) < 2:
            continue
        reading = row[0].strip()
        views = [int_or_null(row[i]) if i < len(row) else "null" for i in view_indices]
        push_entries.append(f'"{reading}":[{",".join(views)}]')
    raw_push = f'const rawPushViews = {{{",".join(push_entries)}}};'

    yt = read_csv(source_dir / battle_cfg["yt_team"])
    yt_series = []
    for row in yt[1:]:
        if len(row) < 5:
            continue
        artist, song, team = row[0], row[1], row[2]
        views = [int_or_null(x) for x in row[4:]]
        yt_series.append(
            f'{{"artist":"{artist}","song":"{song}","team":"{team}","views":[{",".join(views)}]}}'
        )
    raw_yt_views = f'const rawYtTeamViews = [{",".join(yt_series)}];'

    full = read_csv(source_dir / battle_cfg["yt_full"])
    full_series = []
    for row in full[1:]:
        if len(row) < 5:
            continue
        artist, song, team = row[0], row[1], row[2]
        views = [int_or_null(x) for x in row[4:]]
        full_series.append(
            f'{{"artist":"{artist}","song":"{song}","team":"{team}","views":[{",".join(views)}]}}'
        )
    raw_full = f'const rawFullViews = [{",".join(full_series)}];'

    nocut = read_csv(source_dir / battle_cfg["yt_nocut"])
    nocut_series = []
    for row in nocut[1:]:
        if len(row) < 5:
            continue
        artist, song, team = row[0], row[1], row[2]
        views = [int_or_null(x) for x in row[4:]]
        nocut_series.append(
            f'{{"artist":"{artist}","song":"{song}","team":"{team}","views":[{",".join(views)}]}}'
        )
    raw_nocut = f'const rawNocutViews = [{",".join(nocut_series)}];'

    return "\n".join([raw_push, raw_yt_views, raw_full, raw_nocut])


def build_tracker_js(src, battle_src, csv_cfg, battle_cfg, gb_team_csv, pos_cfg, pos_src):
    def js_str(s):
        return str(s).replace('\\', '\\\\').replace('"', '\\"')

    def js_dates(dates):
        return "[" + ",".join(f'"{d}"' for d in dates) + "]"

    def js_int_arr(vals):
        return "[" + ",".join("null" if v is None else str(v) for v in vals) + "]"

    def js_float_arr(vals):
        return "[" + ",".join("null" if v is None else str(v) for v in vals) + "]"

    def view_cols(header):
        return [i for i, h in enumerate(header) if h.endswith("_再生数")]

    def safe_int(s):
        s = str(s).strip()
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    def safe_float(s):
        s = str(s).strip()
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    # ── テーマ曲推しカメラ ──
    theme_rows = read_csv(src / csv_cfg["play"])
    theme_dates = list(theme_rows[0][2:])
    theme_map = {}
    for row in theme_rows[1:]:
        r = row[1].strip() if len(row) > 1 else ""
        if r:
            theme_map[r] = [safe_float(row[i]) if i < len(row) else None for i in range(2, len(theme_rows[0]))]

    # ── GB YouTube 推しカメラ ──
    ytoshi_rows = read_csv(battle_src / battle_cfg["yt_oshicam"])
    ytoshi_vi = view_cols(ytoshi_rows[0])
    ytoshi_dates = [ytoshi_rows[0][i].replace("_再生数", "") for i in ytoshi_vi]
    ytoshi_map = {}
    for row in ytoshi_rows[1:]:
        r = row[0].strip() if row else ""
        if r:
            ytoshi_map[r] = [safe_int(row[i]) if i < len(row) else None for i in ytoshi_vi]

    # ── GB チームメンバー ──
    gb_team_rows = read_csv(battle_src / gb_team_csv)
    gb_member = {}
    for row in gb_team_rows[1:]:
        if len(row) < 6: continue
        r = row[1].strip()
        gb_member[r] = {"name": row[0], "artist": js_str(row[2]), "song": js_str(row[3]),
                        "team": row[4], "broadcast": row[5], "result": row[6].strip() if len(row) > 6 else ""}

    gb_indiv = []
    for r, m in gb_member.items():
        gb_indiv.append(
            f'{{"reading":"{r}","name":"{js_str(m["name"])}","broadcast":"{m["broadcast"]}",'
            f'"song":"{m["song"]}","artist":"{m["artist"]}","team":{m["team"]},'
            f'"ytOshi":{js_int_arr(ytoshi_map.get(r) or [])},'
            f'"theme":{js_float_arr(theme_map.get(r) or [])}}}'
        )

    # ── GB チーム動画 ──
    def load_team_video(path):
        rows = read_csv(path)
        vi = list(range(4, len(rows[0])))
        dates = [rows[0][i].replace("_再生数", "") for i in vi]
        data = {}
        for row in rows[1:]:
            if len(row) < 5: continue
            key = (js_str(row[0]), js_str(row[1]), row[2])
            data[key] = [safe_int(row[i]) if i < len(row) else None for i in vi]
        return dates, data

    yt_dates, yt_map   = load_team_video(battle_src / battle_cfg["yt_team"])
    full_dates, full_map = load_team_video(battle_src / battle_cfg["yt_full"])
    nocut_dates, nocut_map = load_team_video(battle_src / battle_cfg["yt_nocut"])

    seen_teams = {}
    for r, m in gb_member.items():
        key = (m["artist"], m["song"], m["team"])
        if key not in seen_teams:
            seen_teams[key] = {**m, "members": []}
        seen_teams[key]["members"].append(r)

    gb_teams = []
    for (artist, song, team), t in seen_teams.items():
        key = (artist, song, team)
        members_js = "[" + ",".join(f'"{r}"' for r in t["members"]) + "]"
        gb_teams.append(
            f'{{"artist":"{artist}","song":"{song}","team":{team},'
            f'"broadcast":"{t["broadcast"]}","result":"{t["result"]}",'
            f'"members":{members_js},'
            f'"ytTeam":{js_int_arr(yt_map.get(key) or [])},'
            f'"ytFull":{js_int_arr(full_map.get(key) or [])},'
            f'"ytNocut":{js_int_arr(nocut_map.get(key) or [])}}}'
        )

    # ── ポジションバトル 推しカメラ ──
    pos_oshi_rows = read_csv(pos_src / pos_cfg["oshi_cam"])
    pos_oshi_vi = view_cols(pos_oshi_rows[0])
    pos_oshi_dates = [pos_oshi_rows[0][i].replace("_再生数", "") for i in pos_oshi_vi]
    pos_oshi_map = {}
    for row in pos_oshi_rows[1:]:
        r = row[1].strip() if len(row) > 1 else ""
        if r:
            pos_oshi_map[r] = [safe_int(row[i]) if i < len(row) else None for i in pos_oshi_vi]

    # ── ポジションバトル ハイライト ──
    pos_yt_rows = read_csv(pos_src / pos_cfg["yt_highlight"])
    pos_yt_vi = view_cols(pos_yt_rows[0])
    pos_yt_dates = [pos_yt_rows[0][i].replace("_再生数", "") for i in pos_yt_vi]
    pos_yt_map = {}
    for row in pos_yt_rows[1:]:
        if len(row) < 2: continue
        song = js_str(row[1].strip())
        pos_yt_map[song] = [safe_int(row[i]) if i < len(row) else None for i in pos_yt_vi]

    # ── ポジションバトル フル版 ──
    pos_full_rows = read_csv(pos_src / pos_cfg["yt_full"])
    pos_full_vi = view_cols(pos_full_rows[0])
    pos_full_dates = [pos_full_rows[0][i].replace("_再生数", "") for i in pos_full_vi]
    pos_full_map = {}
    for row in pos_full_rows[1:]:
        if len(row) < 2: continue
        song = js_str(row[1].strip())
        pos_full_map[song] = [safe_int(row[i]) if i < len(row) else None for i in pos_full_vi]

    # ── ポジションバトル NOCUT版 ──
    pos_nocut_dates = []
    pos_nocut_map = {}
    if pos_cfg.get("yt_nocut"):
        pos_nocut_rows = read_csv(pos_src / pos_cfg["yt_nocut"])
        pos_nocut_vi = view_cols(pos_nocut_rows[0])
        pos_nocut_dates = [pos_nocut_rows[0][i].replace("_再生数", "") for i in pos_nocut_vi]
        for row in pos_nocut_rows[1:]:
            if len(row) < 2: continue
            song = js_str(row[1].strip())
            pos_nocut_map[song] = [safe_int(row[i]) if i < len(row) else None for i in pos_nocut_vi]

    # ── ポジションバトル チームメンバー ──
    pos_team_rows = read_csv(pos_src / pos_cfg["team"])
    pos_member = {}
    pos_teams_dict = {}
    for row in pos_team_rows[1:]:
        if len(row) < 5: continue
        r = row[1].strip()
        parts = row[2].split(" / ", 1)
        song = js_str(parts[0])
        artist = js_str(parts[1]) if len(parts) > 1 else ""
        bc = row[4]
        pos_member[r] = {"name": row[0], "song": song, "artist": artist, "broadcast": bc}
        if song not in pos_teams_dict:
            pos_teams_dict[song] = {"song": song, "artist": artist, "broadcast": bc, "members": []}
        if r not in pos_teams_dict[song]["members"]:
            pos_teams_dict[song]["members"].append(r)

    pos_indiv = []
    for r, m in pos_member.items():
        pos_indiv.append(
            f'{{"reading":"{r}","name":"{js_str(m["name"])}","broadcast":"{m["broadcast"]}",'
            f'"song":"{m["song"]}","artist":"{m["artist"]}",'
            f'"oshi":{js_int_arr(pos_oshi_map.get(r) or [])}}}'
        )

    pos_teams = []
    for song, t in pos_teams_dict.items():
        members_js = "[" + ",".join(f'"{r}"' for r in t["members"]) + "]"
        pos_teams.append(
            f'{{"song":"{song}","artist":"{t["artist"]}","broadcast":"{t["broadcast"]}",'
            f'"members":{members_js},'
            f'"ytHl":{js_int_arr(pos_yt_map.get(song) or [])},'
            f'"ytFull":{js_int_arr(pos_full_map.get(song) or [])},'
            f'"ytNocut":{js_int_arr(pos_nocut_map.get(song) or [])}}}'
        )

    return "\n".join([
        f"const GB_TRACKER={{ytOshiDates:{js_dates(ytoshi_dates)},themeDates:{js_dates(theme_dates)},ytTeamDates:{js_dates(yt_dates)},ytFullDates:{js_dates(full_dates)},ytNocutDates:{js_dates(nocut_dates)},",
        f"indiv:[{','.join(gb_indiv)}],",
        f"teams:[{','.join(gb_teams)}]}};",
        f"const POS_TRACKER={{oshiDates:{js_dates(pos_oshi_dates)},ytHlDates:{js_dates(pos_yt_dates)},ytFullDates:{js_dates(pos_full_dates)},ytNocutDates:{js_dates(pos_nocut_dates)},",
        f"indiv:[{','.join(pos_indiv)}],",
        f"teams:[{','.join(pos_teams)}]}};",
    ])


def build_concept_js(source_dir, concept_cfg):
    def js_str(s):
        return str(s).replace('\\', '\\\\').replace('"', '\\"')

    def js_dates(dates):
        return "[" + ",".join(f'"{d}"' for d in dates) + "]"

    def load_team_csv(path):
        rows = read_csv(path)
        vi = [i for i, h in enumerate(rows[0]) if h.endswith("_再生数")]
        dates = [rows[0][i].replace("_再生数", "") for i in vi]
        m = {}
        for row in rows[1:]:
            if len(row) < 2:
                continue
            song = js_str(row[0].strip())
            vid  = row[1].strip()
            views = [int_or_null(row[i]) if i < len(row) else "null" for i in vi]
            m[song] = (vid, views)
        return dates, m

    team_rows = read_csv(source_dir / concept_cfg["team"])
    oshi_rows = read_csv(source_dir / concept_cfg["oshi_cam"])

    # 推しカメラ
    oshi_vi    = [i for i, h in enumerate(oshi_rows[0]) if h.endswith("_再生数")]
    oshi_dates = [oshi_rows[0][i].replace("_再生数", "") for i in oshi_vi]
    oshi_map   = {}
    for row in oshi_rows[1:]:
        r = row[1].strip() if len(row) > 1 else ""
        if r:
            oshi_map[r] = [int_or_null(row[i]) if i < len(row) else "null" for i in oshi_vi]

    # ハイライト / One Take Cam / NO CUT / RELAY DANCE / Full (楽曲, 動画ID, date_再生数...)
    hl_dates,    hl_map    = load_team_csv(source_dir / concept_cfg["yt_highlight"])
    otc_dates,   otc_map   = load_team_csv(source_dir / concept_cfg["yt_onetake"])    if concept_cfg.get("yt_onetake")    else ([], {})
    nocut_dates, nocut_map = load_team_csv(source_dir / concept_cfg["yt_nocut"])      if concept_cfg.get("yt_nocut")      else ([], {})
    rd_dates,    rd_map    = load_team_csv(source_dir / concept_cfg["yt_relaydance"]) if concept_cfg.get("yt_relaydance") else ([], {})
    full_dates,  full_map  = load_team_csv(source_dir / concept_cfg["yt_full"])       if concept_cfg.get("yt_full")       else ([], {})

    # メンバー個人データ
    indiv = []
    teams_dict = {}
    for row in team_rows[1:]:
        if len(row) < 3:
            continue
        name        = row[0]
        reading     = row[1].strip()
        song        = row[2].strip()
        position    = row[3].strip()  if len(row) > 3 else ""
        indiv_votes = row[4].strip()  if len(row) > 4 else ""
        team_rank   = row[5].strip()  if len(row) > 5 else ""
        benefit     = row[6].strip()  if len(row) > 6 else ""
        total_votes = row[7].strip()  if len(row) > 7 else ""
        noben_rank  = row[8].strip()  if len(row) > 8 else ""
        conc_rank   = row[9].strip()  if len(row) > 9 else ""

        song_js  = js_str(song)
        oshi     = oshi_map.get(reading, [])
        oshi_js  = "[" + ",".join(str(v) for v in oshi) + "]"

        indiv.append(
            f'{{"reading":"{reading}","name":"{js_str(name)}","song":"{song_js}",'
            f'"pos":"{js_str(position)}",'
            f'"indivVotes":{int_or_null(indiv_votes)},'
            f'"teamRank":{int_or_null(team_rank)},'
            f'"benefit":{int_or_null(benefit)},'
            f'"totalVotes":{int_or_null(total_votes)},'
            f'"nobenRank":{int_or_null(noben_rank)},'
            f'"conceptRank":{int_or_null(conc_rank)},'
            f'"oshi":{oshi_js}}}'
        )

        if song_js not in teams_dict:
            teams_dict[song_js] = []
        teams_dict[song_js].append(reading)

    teams = []
    for song_js, members in teams_dict.items():
        members_js             = "[" + ",".join(f'"{r}"' for r in members) + "]"
        hl_vid,    hl_views    = hl_map.get(song_js,    ("", []))
        otc_vid,   otc_views   = otc_map.get(song_js,   ("", []))
        nocut_vid, nocut_views = nocut_map.get(song_js, ("", []))
        rd_vid,    rd_views    = rd_map.get(song_js,    ("", []))
        full_vid,  full_views  = full_map.get(song_js,  ("", []))
        hl_views_js    = "[" + ",".join(str(v) for v in hl_views)    + "]"
        otc_views_js   = "[" + ",".join(str(v) for v in otc_views)   + "]"
        nocut_views_js = "[" + ",".join(str(v) for v in nocut_views) + "]"
        rd_views_js    = "[" + ",".join(str(v) for v in rd_views)    + "]"
        full_views_js  = "[" + ",".join(str(v) for v in full_views)  + "]"
        teams.append(
            f'{{"song":"{song_js}","members":{members_js},'
            f'"hlVid":"{hl_vid}","hlViews":{hl_views_js},'
            f'"otcVid":"{otc_vid}","otcViews":{otc_views_js},'
            f'"nocutVid":"{nocut_vid}","nocutViews":{nocut_views_js},'
            f'"rdVid":"{rd_vid}","rdViews":{rd_views_js},'
            f'"fullVid":"{full_vid}","fullViews":{full_views_js}}}'
        )

    return "\n".join([
        "const CONCEPT_TRACKER={",
        f"  oshiDates:{js_dates(oshi_dates)},",
        f"  hlDates:{js_dates(hl_dates)},",
        f"  otcDates:{js_dates(otc_dates)},",
        f"  nocutDates:{js_dates(nocut_dates)},",
        f"  rdDates:{js_dates(rd_dates)},",
        f"  fullDates:{js_dates(full_dates)},",
        f"  indiv:[{','.join(indiv)}],",
        f"  teams:[{','.join(teams)}]",
        "};",
    ])


def generate():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    data_dir = BASE_DIR / config["data_dir"]
    play_rows = read_csv(data_dir / config["csv"]["play"])
    vote_rows = read_csv(data_dir / config["csv"]["vote"])
    level_rows = read_csv(data_dir / config["csv"]["broadcast"])

    play_dates, play_dates_js, rawplay_js = build_play_js(play_rows)
    vote_dates_js, rawvote_js = build_vote_js(vote_rows)
    level_js, broadcast_js = build_level_broadcast_js(level_rows)

    last_date = play_dates[-1] if play_dates else "?"

    skip_dates = config.get("heatmap_skip_dates", [])
    skip_js = "const HM_SKIP_DATES = [" + ",".join(f'"{d}"' for d in skip_dates) + "];"

    auto_data = "\n".join([
        play_dates_js,
        vote_dates_js,
        CLASS_ORDER_JS,
        PALETTE_JS,
        skip_js,
        "",
        rawplay_js,
        "",
        level_js,
        "",
        broadcast_js,
        "",
        rawvote_js,
    ])

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    output = template.replace("// {{AUTO_DATA}}", auto_data)
    output = output.replace("{{LAST_DATE}}", last_date)

    if "level_csv" in config:
        src = Path(config.get("local_source_dir", ""))
        output = output.replace("// {{AUTO_LEVEL_DATA}}", build_level_js(src, config["level_csv"]))

    if "group_battle_team_csv" in config:
        src = Path(config.get("local_source_dir", ""))
        output = output.replace("// {{AUTO_GROUP_BATTLE_DATA}}", build_group_battle_profile_js(src, config["group_battle_team_csv"]))

    if "rank_event_csv" in config:
        src = Path(config.get("local_source_dir", config.get("battle_source_dir", "")))
        rank_js = build_rank_events_js(src, config["rank_event_csv"])
        output = output.replace("// {{AUTO_RANK_EVENTS}}", rank_js)

    if "pos_csv" in config:
        src = Path(config.get("local_source_dir", config.get("battle_source_dir", "")))
        pos_js = build_pos_js(src, config["pos_csv"])
        output = output.replace("// {{AUTO_POS_DATA}}", pos_js)
        if "oshi_cam" in config["pos_csv"]:
            pos_oshi_js = build_pos_oshi_js(src, config["pos_csv"])
            output = output.replace("// {{AUTO_POS_OSHI_DATA}}", pos_oshi_js)

    if "battle_source_dir" in config and "battle_csv" in config:
        source_dir = Path(config["battle_source_dir"])
        battle_cfg = config["battle_csv"]
        snap_js = build_battle_snap_js(source_dir, battle_cfg)
        dates_js = build_battle_dates_js(source_dir, battle_cfg)
        series_js = build_battle_series_js(source_dir, battle_cfg)
        output = output.replace("// {{AUTO_BATTLE_SNAP}}", snap_js)
        output = output.replace("// {{AUTO_BATTLE_DATES}}", dates_js)
        output = output.replace("// {{AUTO_BATTLE_SERIES}}", series_js)

    if "concept_csv" in config:
        src = Path(config.get("local_source_dir", config.get("battle_source_dir", "")))
        concept_js = build_concept_js(src, config["concept_csv"])
        output = output.replace("// {{AUTO_CONCEPT_DATA}}", concept_js)

    if ("battle_source_dir" in config and "battle_csv" in config
            and "group_battle_team_csv" in config and "pos_csv" in config):
        src_l = Path(config.get("local_source_dir", config["battle_source_dir"]))
        battle_src = Path(config["battle_source_dir"])
        pos_src = Path(config.get("local_source_dir", config["battle_source_dir"]))
        tracker_js = build_tracker_js(
            src_l, battle_src, config["csv"], config["battle_csv"],
            config["group_battle_team_csv"], config["pos_csv"], pos_src
        )
        output = output.replace("// {{AUTO_TRACKER_DATA}}", tracker_js)

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"生成完了: {OUTPUT_PATH}")
    print(f"  再生数: {len(play_dates)}週分 / 最終更新: {last_date}")
    print(f"  投票: {vote_dates_js[:60]}...")


if __name__ == "__main__":
    generate()
