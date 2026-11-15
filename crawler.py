
import json
import os
from pathlib import Path

import requests

URL = (
    "https://mapleplanet.io/news/notices"
    "?filter=notice&_rsc=QHt1mNIJLL0VvtDc"
)
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DATA_FILE = Path(__file__).with_name("sent_notices.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/x-component",
    "RSC": "1",
    "Next-Url": "/news/notices",
    "Referer": "https://mapleplanet.io/news/notices",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def load_history():
    if not DATA_FILE.exists():
        return set()

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return {str(item) for item in data}

        if isinstance(data, dict):
            for key in ("ids", "notices", "sent"):
                if isinstance(data.get(key), list):
                    return {str(item) for item in data[key]}

            return {str(key) for key in data.keys()}

    except (json.JSONDecodeError, OSError):
        pass

    return set()


def save_history(sent_ids):
    DATA_FILE.write_text(
        json.dumps(
            {"ids": sorted(sent_ids, key=lambda x: int(x))},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def get_notices():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    # 응답을 UTF-8로 직접 디코딩
    body = response.content.decode("utf-8")

    marker = '"posts":'
    position = body.find(marker)

    if position == -1:
        raise RuntimeError("응답에서 공지 목록을 찾지 못했습니다.")

    start = position + len(marker)
    posts, _ = json.JSONDecoder().raw_decode(body[start:])

    notices = []

    for post in posts:
        if post.get("category") != "notices":
            continue

        if post.get("isHidden"):
            continue

        notice_id = str(post.get("id", ""))
        title = post.get("title", "").strip()

        if notice_id and title:
            notices.append({
                "id": notice_id,
                "title": title,
                "date": post.get("publishedAt", ""),
                "url": f"https://mapleplanet.io/news/notices/{notice_id}",
            })

    if not notices:
        raise RuntimeError("공지 목록이 비어 있습니다.")

    print(f"공지 {len(notices)}개 수집 완료")
    return notices


def send_discord(notice):
    if not WEBHOOK:
        raise RuntimeError("DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")

    message = (
        "📢 **메이플 플래닛 새 공지!**\n"
        f"**{notice['title']}**\n"
        f"📅 {notice['date']}\n"
        f"🔗 {notice['url']}"
    )

    response = requests.post(
        WEBHOOK,
        json={"content": message},
        timeout=30,
    )
    response.raise_for_status()

    print(f"디스코드 알림 전송 완료: {notice['title']}")


def main():
    notices = get_notices()
    sent_ids = load_history()

    # 첫 실행은 현재 공지를 기준 목록으로 저장
    if not sent_ids:
        save_history({notice["id"] for notice in notices})
        print("최초 실행: 기존 공지 목록 저장 완료. 알림은 보내지 않았습니다.")
        return

    new_notices = [
        notice for notice in notices
        if notice["id"] not in sent_ids
    ]

    if not new_notices:
        print("새 공지가 없습니다.")
        return

    print(f"새 공지 {len(new_notices)}개 발견!")

    # 오래된 새 공지부터 전송
    for notice in reversed(new_notices):
        send_discord(notice)
        sent_ids.add(notice["id"])
        save_history(sent_ids)

    print("새 공지 확인 및 알림 전송 완료!")


if __name__ == "__main__":
    main()
