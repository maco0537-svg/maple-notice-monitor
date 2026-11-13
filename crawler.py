
import os
import json
import time
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://mapleplanet.io/news/notices"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DATA_FILE = Path(__file__).with_name("sent_notices.json")
INTERVAL = 300

if not WEBHOOK:
    raise ValueError("DISCORD_WEBHOOK_URL 환경변수를 설정해 주세요.")

def load_sent():
    if DATA_FILE.exists():
        return set(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return None

def save_sent(sent):
    DATA_FILE.write_text(
        json.dumps(sorted(sent), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def get_notices(page):
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    results = []
    links = page.locator('a[href^="/news/notices/"]')

    for i in range(links.count()):
        item = links.nth(i)
        title = item.locator("span.text-base").first
        date = item.locator("time").first

        if not title.count() or not date.count():
            continue

        href = item.get_attribute("href")
        notice_id = href.rstrip("/").split("/")[-1]

        results.append({
            "id": notice_id,
            "url": "https://mapleplanet.io" + href
        })

    return results

def send_discord(notice):
    response = requests.post(
        WEBHOOK,
        json={"content": notice["url"]},
        timeout=15
    )
    response.raise_for_status()

def main():
    sent = load_sent()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            while True:
                try:
                    notices = get_notices(page)

                    # 첫 실행이면 기존 공지를 기록만 하고 알림은 보내지 않음
                    if sent is None:
                        sent = {notice["id"] for notice in notices}
                        save_sent(sent)

                    else:
                        for notice in reversed(notices):
                            if notice["id"] not in sent:
                                send_discord(notice)
                                sent.add(notice["id"])
                                save_sent(sent)

                except Exception as e:
                    print("오류 발생:", e)

                time.sleep(INTERVAL)

        finally:
            browser.close()

if __name__ == "__main__":
    main()
