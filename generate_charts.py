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
        vals = ",".join(format_val(v, as_float=False) for v in row[2:])
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

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"生成完了: {OUTPUT_PATH}")
    print(f"  再生数: {len(play_dates)}週分 / 最終更新: {last_date}")
    print(f"  投票: {vote_dates_js[:60]}...")


if __name__ == "__main__":
    generate()
