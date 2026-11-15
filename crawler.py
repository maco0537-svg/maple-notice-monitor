import json
import os
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://mapleplanet.io/news/notices"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DATA_FILE = Path(__file__).with_name("sent_notices.json")


def load_sent():
    if DATA_FILE.exists():
        return set(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return None


def save_sent(sent):
    DATA_FILE.write_text(
        json.dumps(sorted(sent), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_notices(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    print("현재 페이지:", page.url)
    print("페이지 제목:", page.title())

    all_links = page.locator("a").evaluate_all("""
        elements => elements.map(a => ({
            href: a.href,
            text: a.innerText.trim()
        }))
    """)

    notice_links = [
        link for link in all_links
        if "/news/notices/" in link["href"]
    ]

    print("전체 링크 수:", len(all_links))
    print("공지 링크 수:", len(notice_links))

    for link in notice_links[:10]:
        print("공지 링크 확인:", link)

    results = []

    for link in notice_links:
        href = link["href"]
        notice_id = href.rstrip("/").split("/")[-1]
        title = " ".join(link["text"].split())

        if notice_id.isdigit() and title:
            results.append({
                "id": notice_id,
                "title": title,
                "url": href,
            })

    if not results:
        print("페이지 HTML 일부:", page.locator("body").inner_text()[:1000])
        raise RuntimeError("공지 목록을 찾지 못했습니다.")

    print(f"공지 {len(results)}개 발견!")
    return results

def send_discord(notice):
    response = requests.post(
        WEBHOOK,
        json={
            "content": f"📢 **메이플 플래닛 새 공지!**\n{notice['title']}\n{notice['url']}"
        },
        timeout=20,
    )
    response.raise_for_status()


def main():
    if not WEBHOOK:
        raise ValueError("DISCORD_WEBHOOK_URL이 없습니다.")

    sent = load_sent()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            notices = get_notices(page)

            if sent is None:
                sent = {n["id"] for n in notices}
                save_sent(sent)
                print(f"기존 공지 {len(sent)}개 저장 완료. 알림은 보내지 않았습니다.")
                return

            new_notices = [
                n for n in reversed(notices)
                if n["id"] not in sent
            ]

            if not new_notices:
                print("새 공지가 없습니다.")
                return

            for notice in new_notices:
                send_discord(notice)
                sent.add(notice["id"])
                save_sent(sent)
                print("전송 완료:", notice["title"])

        finally:
            browser.close()


if __name__ == "__main__":
    main()
