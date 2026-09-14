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
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# 공통 JSON 요청
# ============================================================

def get_json(url, timeout=40):
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
    fng = data.get("fear_and_greed")

    if not isinstance(fng, dict):
        raise ValueError(
            "CNN 응답에 fear_and_greed가 없습니다."
        )

    if fng.get("score") is None:
        raise ValueError(
            "CNN 응답에 score가 없습니다."
        )

    result = {
        "score": round(
            float(fng["score"]),
            1,
        ),
        "rating": str(
            fng.get("rating", "")
        ),
        "previousClose": None,
        "week": None,
        "month": None,
        "year": None,
        "cnnTimestamp": fng.get("timestamp"),
        "source": "CNN Fear & Greed Index",
        "stale": False,
    }

    if fng.get("previous_close") is not None:
        result["previousClose"] = round(
            float(fng["previous_close"]),
            1,
        )

    if fng.get("previous_1_week") is not None:
        result["week"] = round(
            float(fng["previous_1_week"]),
            1,
        )

    if fng.get("previous_1_month") is not None:
        result["month"] = round(
            float(fng["previous_1_month"]),
            1,
        )

    if fng.get("previous_1_year") is not None:
        result["year"] = round(
            float(fng["previous_1_year"]),
            1,
        )

    return result


def fetch_fng():
    cache_buster = str(int(time.time()))

    direct_url = (
        CNN_FNG_URL
        + "?t="
        + cache_buster
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

    errors = []

    for route_number, url in enumerate(
        urls,
        start=1,
    ):
        for attempt in range(1, 4):
            try:
                response_data = get_json(
                    url,
                    timeout=40,
                )

                return parse_fng_response(
                    response_data
                )

            except Exception as error:
                errors.append(
                    "경로 "
                    + str(route_number)
                    + " / 시도 "
                    + str(attempt)
                    + " / "
                    + repr(error)
                )

                if attempt < 3:
                    time.sleep(attempt * 3)

    raise RuntimeError(
        "CNN 조회 실패: "
        + " | ".join(errors)
    )


# ============================================================
# 네이버 금융 VIX와 나스닥100
# ============================================================

def fetch_closes(symbol):
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
                + " 응답이 리스트가 아닙니다."
            )

        if len(rows) == 0:
            break

        for row in rows:
            close_price = row.get("closePrice")

            if close_price is None:
                continue

            if close_price == "":
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

    if len(closes) < 252:
        raise ValueError(
            symbol
            + " 데이터 부족: "
            + str(len(closes))
            + "개"
        )

    # 네이버 응답은 최신 날짜부터 과거 날짜 순서입니다.
    # 계산을 위해 과거부터 최신 날짜 순서로 뒤집습니다.
    closes.reverse()

    return closes


# ============================================================
# 메인 실행
# ============================================================

def main():
    errors = []

    previous = load_previous_data()

    # --------------------------------------------------------
    # CNN 공포탐욕지수
    # --------------------------------------------------------

    try:
        fng = fetch_fng()

    except Exception as error:
        previous_fng = previous.get("fng")

        if isinstance(previous_fng, dict):
            fng = dict(previous_fng)
            fng["stale"] = True
            fng["source"] = "직전 CNN 정상값"

            errors.append(
                "공포탐욕지수 최신 조회 실패. "
                "직전 정상값 사용: "
                + repr(error)
            )

        else:
            fng = None

            errors.append(
                "공포탐욕지수 조회 실패: "
                + repr(error)
            )

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    try:
        vix_closes = fetch_closes(".VIX")

        vix = round(
            vix_closes[-1],
            2,
        )

    except Exception as error:
        vix = previous.get("vix")

        if vix is not None:
            errors.append(
                "VIX 최신 조회 실패. "
                "직전 정상값 사용: "
                + repr(error)
            )

        else:
            errors.append(
                "VIX 조회 실패: "
                + repr(error)
            )

    # --------------------------------------------------------
    # 나스닥100
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
                2,
            ),
            "days": len(ndx_closes),
        }

    except Exception as error:
        ndx = previous.get("ndx")

        if ndx is not None:
            errors.append(
                "나스닥100 최신 조회 실패. "
                "직전 정상값 사용: "
                + repr(error)
            )

        else:
            errors.append(
                "나스닥100 조회 실패: "
                + repr(error)
            )

    # --------------------------------------------------------
    # data.json 저장
    # --------------------------------------------------------

    now = datetime.now(KST)

    output = {
        "updatedAt": now.isoformat(
            timespec="seconds"
        ),
        "updatedLabel": (
            now.strftime(
                "%Y년 %m월 %d일 %H:%M"
            )
            + " (한국시각)"
        ),
        "fng": fng,
        "vix": vix,
        "ndx": ndx,
        "errors": errors,
    }

    with open(
        "data.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
