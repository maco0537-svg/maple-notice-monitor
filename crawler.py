
import requests
from pathlib import Path

URL = "https://mapleplanet.io/news/notices?filter=notice&_rsc=QHt1mNIJLL0VvtDc"

headers = {
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

Path("sent_notices.json").touch(exist_ok=True)

try:
    response = requests.get(URL, headers=headers, timeout=30)

    print("HTTP 상태 코드:", response.status_code)
    print("응답 형식:", response.headers.get("content-type"))
    print("응답 전체 길이:", len(response.text))

for keyword in ["publishedAt", "title", "라이브", "공지", "posts"]:
    position = response.text.find(keyword)

    print(f"\n[{keyword}] 위치:", position)

    if position != -1:
        print(response.text[max(0, position - 300):position + 700])

    if "Performing security verification" in response.text:
        print("결과: Cloudflare 보안 차단")
    elif response.status_code == 200:
        print("결과: 응답 수신 성공")
    else:
        print("결과: 응답 확인 필요")

except Exception as error:
    print("요청 오류:", repr(error))
    raise
