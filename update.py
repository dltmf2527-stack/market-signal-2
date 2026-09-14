import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta


# ============================================================
# 기본 설정
# ============================================================

KST = timezone(timedelta(hours=9))

CNN_FNG_URL = (
    "https://production.dataviz.cnn.io/"
    "index/fearandgreed/graphdata"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Referer": "https://edition.cnn.com/",
    "Origin": "https://edition.cnn.com",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# 공통 요청 함수
# ============================================================

def get_json(url, timeout=40):
    """
    URL에서 JSON 데이터를 읽습니다.
    HTTP 오류가 발생하면 호출한 함수로 오류를 전달합니다.
    """

    request = urllib.request.Request(
        url=url,
        headers=HEADERS,
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        body = response.read().decode(
            "utf-8",
            errors="replace",
        )

    return json.loads(body)


# ============================================================
# 이전 data.json 읽기
# ============================================================

def load_previous_data():
    """
    일시적인 외부 API 오류가 발생했을 때
    마지막 정상값을 유지하기 위해 기존 data.json을 읽습니다.
    """

    try:
        with open(
            "data.json",
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception:
        return {}


# ============================================================
# CNN 공포탐욕지수
# ============================================================

def parse_fng_response(data):
    """
    CNN 응답에서 필요한 공포탐욕지수 값만 추출합니다.
    """

    fng = data.get("fear_and_greed")

    if not isinstance(fng, dict):
        raise ValueError(
            "CNN 응답에 fear_and_greed 항목이 없습니다."
        )

    if fng.get("score") is None:
        raise ValueError(
            "CNN 응답에 score 값이 없습니다."
        )

    return {
        "score": round(
            float(fng["score"]),
            1,
        ),
        "rating": str(
            fng.get("rating", "")
        ),
        "previousClose": (
            round(
                float(fng["previous_close"]),
                1,
            )
            if fng.get("previous_close") is not None
            else None
        ),
        "week": (
            round(
                float(fng["previous_1_week"]),
                1,
            )
            if fng.get("previous_1_week") is not None
            else None
        ),
        "month": (
            round(
                float(fng["previous_1_month"]),
                1,
            )
            if fng.get("previous_1_month") is not None
            else None
        ),
        "year": (
            round(
                float(fng["previous_1_year"]),
                1,
            )
            if fng.get("previous_1_year") is not None
            else None
        ),
        "cnnTimestamp": fng.get("timestamp"),
        "source": "CNN Fear & Greed Index",
        "stale": False,
    }


def fetch_fng():
    """
    CNN 공식 주소에 최신 공포탐욕지수를 요청합니다.

    1. CNN 공식 주소에 직접 요청
    2. 실패하면 AllOrigins raw 경로로 요청
    3. 각 경로를 최대 3번 재시도
    """

    cache_buster = int(time.time())

    direct_url = (
        CNN_FNG_URL
        + "?t="
        + str(cache_buster)
    )

    proxy_url = (
        "https://api.allorigins.win/raw?url="
        + urllib.parse.quote(
            direct_url,
            safe="",
        )
    )

    urls = [
        direct_url,
        proxy_url,
    ]

    error_messages = []

    for url_number, url in enumerate(
        urls,
        start=1,
    ):
        for attempt in range(1, 4):
            try:
                data = get_json(
                    url,
                    timeout=40,
                )

                return parse_fng_response(data)

            except Exception as error:
                error_messages.append(
                    "경로 "
                    + str(url_number)
                    + ", 시도 "
                    + str(attempt)
                    + ": "
                    + repr(error)
                )

                if attempt < 3:
                    time.sleep(
                        attempt * 4
                    )

    raise RuntimeError(
        "CNN 공포탐욕지수 조회 실패 | "
        + " | ".join(error_messages)
    )


# ============================================================
# 네이버 금융 VIX 및 나스닥100
# ============================================================

def fetch_closes(symbol, required_days=300):
    """
    네이버 금융에서 지수 일별 종가를 가져옵니다.

    네이버 API에서 검증된 형식:
    pageSize=10&page=1

    한 페이지당 10일이므로
    30페이지를 조회해 최대 약 300개 값을 수집합니다.
    """

    closes = []

    for page in range(1, 31):
        url = (
            "https://api.stock.naver.com/"
            "index/"
            + symbol
            + "/price?pageSize=10&page="
            + str(page)
        )

        rows = get_json(
            url,
            timeout=30,
        )

        if not isinstance(rows, list):
            raise ValueError(
                symbol
                + " 응답이 리스트 형식이 아닙니다."
            )

        if not rows:
            break

        for row in rows:
            close_price = row.get("closePrice")

            if close_price in (
                None,
                "",
            ):
                continue

            try:
                value = float(
                    str(close_price).replace(
                        ",",
                        "",
                    )
                )

                closes.append(value)

            except ValueError:
                continue

        time.sleep(0.3)

    if len(closes) < 210:
        raise ValueError(
            symbol
            + " 데이터 부족: "
            + str(len(closes))
            + "개"
        )

    /*
    네이버 응답은 최신 날짜부터 과거 날짜 순서입니다.
    계산을 위해 과거부터 최신 순서로 뒤집습니다.
    */
    closes.reverse()

    if len(closes) > required_days:
        closes = closes[-required_days:]

    return closes


# ============================================================
# 메인 실행
# ============================================================

def main():
    errors = []

    previous = load_previous_data()

    # --------------------------------------------------------
    # 1. CNN 공포탐욕지수
    # --------------------------------------------------------

    try:
        fng = fetch_fng()

    except Exception as error:
        previous_fng = previous.get("fng")

        if isinstance(previous_fng, dict):
            fng = dict(previous_fng)
            fng["stale"] = True

            errors.append(
                "공포탐욕지수 최신 조회 실패. "
                "직전 정상값 표시 중: "
                + repr(error)
            )

        else:
            fng = None

            errors.append(
                "공포탐욕지수 조회 실패: "
                + repr(error)
            )

    # --------------------------------------------------------
    # 2. VIX
    # --------------------------------------------------------

    try:
        vix_closes = fetch_closes(".VIX")

        vix = round(
            vix_closes[-1],
            2,
        )

    except Exception as error:
        vix = previous.get("vix")

        errors.append(
            "VIX 최신 조회 실패"
            + (
                ". 직전 정상값 표시 중: "
                if vix is not None
                else ": "
            )
            + repr(error)
        )

    # --------------------------------------------------------
    # 3. 나스닥100
    # --------------------------------------------------------

    try:
        ndx_closes = fetch_closes(".NDX")

        last = ndx_closes[-1]

        last_200 = ndx_closes[-200:]
        ma200 = (
            sum(last_200)
            / len(last_200)
        )

        last_252 = ndx_closes[-252:]
        high_52w = max(last_252)

        ndx = {
            "last": round(
                last,
                2,
            ),
            "ma200": round(
                ma200,
                2,
            ),
            "high52w": round(
                high_52w,
                2,
            ),
            "drawdown": round(
                (
                    last / high_52w
                    - 1
                )
                * 100,
                2,
            ),
            "maGap": round(
                (
                    last / ma200
                    - 1
                )
                * 100,
        
