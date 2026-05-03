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


def build_play_js(rows):
    header = rows[0]
    dates = header[2:]
    dates_js = "const PLAY_DATES = [" + ",".join(f'"{d}"' for d in dates) + "];"

    entries = []
    for row in rows[1:]:
        name, code = row[0], row[1]
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
        name, code = row[0], row[1]
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
        name = row[0]
        level = row[2]
        group = row[3]
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
        team_entries.append(f'["{name}","{reading}","{song}","{artist}","{position}","{broadcast}"]')

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
    mnet = read_csv(source_dir / battle_cfg["mnetplus"])
    header = mnet[0]
    n = len(header)
    latest_label = header[n - 3].replace("_再生数", "")
    oshi_entries = []
    for row in mnet[1:]:
        if len(row) < 4:
            continue
        reading = row[1]
        lv = int_or_null(row[n - 3]) if n - 3 < len(row) else "null"
        ll = int_or_null(row[n - 2]) if n - 2 < len(row) else "null"
        lc = int_or_null(row[n - 1]) if n - 1 < len(row) else "null"
        oshi_entries.append(f'"{reading}":[{lv},{ll},{lc}]')
    raw_oshi = (
        f"// 推しカメラ再生数（mnetplus {latest_label}）: reading → [views, likes, comments]\n"
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
    mnet = read_csv(source_dir / battle_cfg["mnetplus"])
    push_dates = [mnet[0][i].replace("_再生数", "") for i in range(2, len(mnet[0]), 3)]

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
    mnet = read_csv(source_dir / battle_cfg["mnetplus"])
    n_header = len(mnet[0])
    view_indices = list(range(2, n_header, 3))
    push_entries = []
    for row in mnet[1:]:
        if len(row) < 4:
            continue
        reading = row[1]
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

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"生成完了: {OUTPUT_PATH}")
    print(f"  再生数: {len(play_dates)}週分 / 最終更新: {last_date}")
    print(f"  投票: {vote_dates_js[:60]}...")


if __name__ == "__main__":
    generate()
