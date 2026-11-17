
import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mapleplanet.io"
NOTICE_URL = (
    f"{BASE_URL}/news/notices"
    "?filter=notice&_rsc=QHt1mNIJLL0VvtDc"
)
PATCHNOTE_LIST_URL = f"{BASE_URL}/news/updates"

WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DATA_FILE = Path(__file__).with_name("sent_notices.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
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


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_date(value):
    if not value:
        return ""

    match = re.search(
        r"(20\d{2})[.년/-]\s*(\d{1,2})[.월/-]\s*(\d{1,2})",
        str(value),
    )

    if not match:
        return ""

    year, month, day = match.groups()
    return f"{int(year):04d}.{int(month):02d}.{int(day):02d}"


def get_notices():
    response = requests.get(
        NOTICE_URL,
        headers={
            **HEADERS,
            "Accept": "text/x-component",
            "RSC": "1",
            "Next-Url": "/news/notices",
            "Referer": f"{BASE_URL}/news/notices",
        },
        timeout=30,
    )
    response.raise_for_status()

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
        title = clean_text(post.get("title", ""))

        if notice_id and title:
            notices.append({
                "id": notice_id,
                "title": title,
                "date": post.get("publishedAt", ""),
                "url": f"{BASE_URL}/news/notices/{notice_id}",
            })

    if not notices:
        raise RuntimeError("공지 목록이 비어 있습니다.")

    print(f"공지 {len(notices)}개 수집 완료")
    return notices


def get_patchnotes_for_date(target_date):
    """공지 날짜와 같은 날짜에 올라온 패치노트를 찾아 요약합니다."""
    if not target_date:
        return []

    response = requests.get(
        PATCHNOTE_LIST_URL,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    patchnotes = []
    seen_urls = set()

    for anchor in soup.select('a[href*="/news/updates/"]'):
        href = anchor.get("href", "")

        if not re.fullmatch(r"/news/updates/\d+/?", href):
            continue

        url = BASE_URL + href

        if url in seen_urls:
            continue

        seen_urls.add(url)

        card_text = clean_text(anchor.get_text(" ", strip=True))
        if normalize_date(card_text) != target_date:
            continue

        detail_response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
        )
        detail_response.raise_for_status()

        detail_soup = BeautifulSoup(
            detail_response.text,
            "html.parser",
        )

        main = (
            detail_soup.find("main")
            or detail_soup.find("article")
            or detail_soup.body
            or detail_soup
        )

        title_tag = main.find("h1")
        title = (
            clean_text(title_tag.get_text(" ", strip=True))
            if title_tag
            else card_text
        )

        for unwanted in main.select(
            "script, style, nav, footer, header, button"
        ):
            unwanted.decompose()

        items = []
        seen_items = set()

        # 중첩된 세부 설명은 제외하고 큰 항목 위주로 추출합니다.
        for item in main.select("li"):
            if item.find_parent("li") is not None:
                continue

            text = clean_text(item.get_text(" ", strip=True))

            if len(text) < 8 or text in seen_items:
                continue

            seen_items.add(text)
            items.append(text)

        # 목록이 없는 페이지라면 문단을 대신 사용합니다.
        if not items:
            for paragraph in main.select("p"):
                text = clean_text(paragraph.get_text(" ", strip=True))

                if len(text) >= 15 and text not in seen_items:
                    seen_items.add(text)
                    items.append(text)

        if items:
            patchnotes.append({
                "title": title,
                "url": url,
                "items": items[:6],
            })

    print(f"{target_date} 패치노트 {len(patchnotes)}개 확인")
    return patchnotes


def send_discord(notice):
    if not WEBHOOK:
        raise RuntimeError("DISCORD_WEBHOOK_URL이 설정되지 않았습니다.")

    lines = [
        "📢 **메이플 플래닛 새 공지!**",
        f"**{notice['title']}**",
        f"📅 {notice['date']}",
    ]

    notice_date = (
        normalize_date(notice.get("date"))
        or normalize_date(notice.get("title"))
    )

    try:
        patchnotes = get_patchnotes_for_date(notice_date)

        for patchnote in patchnotes:
            lines.extend([
                "",
                f"📝 **패치노트 요약: {patchnote['title']}**",
            ])

            for item in patchnote["items"]:
                lines.append(f"• {item[:180]}")

            lines.append(
                f"🔗 [패치노트 원문]({patchnote['url']})"
            )

    except Exception as error:
        # 패치노트 수집에 실패해도 기존 공지 알림은 보냅니다.
        print(f"패치노트 요약 생략: {error}")

    lines.extend([
        "",
        f"🔗 [기존 공지 원문]({notice['url']})",
    ])

    message = "\n".join(lines)

    if len(message) > 1900:
        message = message[:1850] + "\n…\n(내용 일부 생략)"

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

    # 최초 실행은 기존 공지를 저장만 하고 알림은 보내지 않습니다.
    if not sent_ids:
        save_history({notice["id"] for notice in notices})
        print("최초 실행: 기존 공지 목록 저장 완료.")
        return

    new_notices = [
        notice for notice in notices
        if notice["id"] not in sent_ids
    ]

    if not new_notices:
        print("새 공지가 없습니다.")
        return

    print(f"새 공지 {len(new_notices)}개 발견!")

    for notice in reversed(new_notices):
        send_discord(notice)
        sent_ids.add(notice["id"])
        save_history(sent_ids)

    print("새 공지 확인 및 알림 전송 완료!")


if __name__ == "__main__":
    main()
