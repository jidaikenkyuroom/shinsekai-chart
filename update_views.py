#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube再生数記録スクリプト（GitHub Actions用）
プレイリストの全動画の再生回数を取得してCSVに追記する
"""

import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from googleapiclient.discovery import build

BASE_DIR    = Path(__file__).parent
CSV_PATH    = BASE_DIR / "data" / "新世界テーマ曲_推しカメラ再生数.csv"
API_KEY     = os.environ["YOUTUBE_API_KEY"]
PLAYLIST_ID = "PL3fCPdnAFT0YNA-DdjkWikiwcsct0vow0"


def get_playlist_videos(youtube, playlist_id):
    videos = []
    next_page_token = None
    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token,
        ).execute()
        for item in resp["items"]:
            snippet  = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            title    = snippet["title"]
            videos.append((video_id, title))
        next_page_token = resp.get("nextPageToken")
        if not next_page_token:
            break
    return videos


def get_view_counts(youtube, video_ids):
    view_counts = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        resp = youtube.videos().list(
            part="statistics",
            id=",".join(chunk),
        ).execute()
        for item in resp["items"]:
            vid   = item["id"]
            views = int(item["statistics"].get("viewCount", 0))
            view_counts[vid] = views
    return view_counts


def views_to_man(views: int) -> float:
    return round(views / 10000, 1)


def match_reading(reading: str, title: str) -> bool:
    candidates = [reading]
    if "." in reading:
        parts = reading.split(".", 1)
        candidates.append(f"{parts[1]}.{parts[0]}")
    for candidate in candidates:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(candidate) + r"(?![A-Za-z0-9])"
        if re.search(pattern, title, flags=re.IGNORECASE):
            return True
    return False


def today_label() -> str:
    now = datetime.now()
    return f"{now.month}月{now.day}日"


def main():
    today = today_label()
    print(f"実行日: {today}")

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    if not rows:
        print("エラー: CSVが空です")
        sys.exit(1)

    header = rows[0]

    if today in header:
        print(f"「{today}」列は既に存在します。処理をスキップします。")
        sys.exit(0)

    youtube = build("youtube", "v3", developerKey=API_KEY)

    print("プレイリストから動画情報を取得中...")
    videos = get_playlist_videos(youtube, PLAYLIST_ID)
    print(f"  取得動画数: {len(videos)} 件")

    print("再生回数を取得中...")
    video_ids   = [vid for vid, _ in videos]
    view_counts = get_view_counts(youtube, video_ids)

    reading_to_man: dict[str, float] = {}
    print("\n--- マッチング結果 ---")
    for video_id, title in videos:
        if video_id not in view_counts:
            continue
        man = views_to_man(view_counts[video_id])
        matched_reading = None
        for row in rows[1:]:
            if len(row) < 2:
                continue
            reading = row[1].strip()
            if reading and match_reading(reading, title):
                matched_reading = reading
                break
        if matched_reading:
            if matched_reading in reading_to_man:
                print(f"  [警告] 「{matched_reading}」に複数動画がマッチ: {title}")
            else:
                reading_to_man[matched_reading] = man
                print(f"  OK  {matched_reading:15s} ← {title}  ({man}万回)")
        else:
            print(f"  --  未マッチ: {title}")

    header.append(today)
    matched_count   = 0
    unmatched_names = []
    for row in rows[1:]:
        if len(row) < 2:
            row.append("")
            continue
        reading = row[1].strip()
        if reading in reading_to_man:
            row.append(str(reading_to_man[reading]))
            matched_count += 1
        else:
            row.append("")
            if reading:
                unmatched_names.append(reading)

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)

    print(f"\n完了: {matched_count} 件追記 / 未マッチ {len(unmatched_names)} 件")
    if unmatched_names:
        print(f"未マッチの読み方: {', '.join(unmatched_names)}")


if __name__ == "__main__":
    main()
