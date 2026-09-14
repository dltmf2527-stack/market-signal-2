import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))

CNN_URL = (
    "https://production.dataviz.cnn.io/"
    "index/fearandgreed/graphdata"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Referer": "https://edition.cnn.com/",
}


def get_json(url, timeout=35):
    request = urllib.request.Request(
        url,
        headers=HEADERS,
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        text = response.read().decode(
            "utf-8",
            errors="replace",
        )

    return json.loads(text)


def load_previous():
    try:
        with open(
            "data.json",
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception:
        return {}


def optional_number(data, key):
    value = data.get(key)

    if value is None:
        return None

    return round(
        float(value),
        1,
    )


def parse_fng(data):
    fng = data.get("fear_and_greed")

    if not isinstance(fng, dict):
        raise ValueError(
            "CNN 응답에 fear_and_greed가 없습니다."
        )

    if fng.get("score") is None:
        raise ValueError(
            "CNN 응답에 score가 없습니다."
        )

    return {
        "score": round(
            float(fng["score"]),
            1,
        ),
        "rating": str(
            fng.get("rating", "")
        ),
        "previousClose": optional_number(
            fng,
            "previous_close",
        ),
        "week": optional_number(
            fng,
            "previous_1_week",
        ),
        "month": optional_number(
            fng,
            "previous_1_month",
        ),
        "year": optional_number(
            fng,
            "previous_1_year",
        ),
        "cnnTimestamp": fng.get(
            "timestamp"
        ),
        "source": "CNN Fear & Greed Index",
        "stale": False,
    }


def fetch_fng():
    timestamp = str(
        int(time.time())
    )

    direct_url = (
        CNN_URL
        + "?t="
        + timestamp
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

    for url in urls:
        for attempt in range(2):
            try:
                data = get_json(
                    url,
                    timeout=35,
                )

                return parse_fng(data)

            except Exception as error:
                errors.append(
                    repr(error)
                )

                if attempt == 0:
                    time.sleep(3)

    raise RuntimeError(
        "CNN 조회 실패: "
        + " | ".join(errors)
    )


def fetch_closes(symbol):
    newest_first = []

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

        if not rows:
            break

        for row in rows:
            raw = row.get(
                "closePrice"
            )

            if raw in (None, ""):
                continue

            try:
                value = float(
                    str(raw).replace(
                        ",",
                        "",
                    )
                )

                newest_first.append(
                    value
                )

            except ValueError:
                continue

        time.sleep(0.2)

    if len(newest_first) < 252:
        raise ValueError(
            symbol
            + " 데이터 부족: "
            + str(len(newest_first))
            + "개"
        )

    # 네이버 응답은 최신 날짜부터 과거 날짜 순서입니다.
    # 계산을 위해 과거 날짜부터 최신 날짜 순서로 바꿉니다.
    newest_first.reverse()

    return newest_first


def main():
    previous = load_previous()
    errors = []

    # CNN 공포탐욕지수
    try:
        fng = fetch_fng()

    except Exception as error:
        old_fng = previous.get(
            "fng"
        )

        if isinstance(
            old_fng,
            dict,
        ):
            fng = dict(old_fng)
            fng["stale"] = True
            fng["source"] = (
                "직전 CNN 정상값"
            )

            errors.append(
                "공탐 최신 조회 실패, "
                "직전값 사용: "
                + repr(error)
            )

        else:
            fng = None

            errors.append(
                "공탐 조회 실패: "
                + repr(error)
            )

    # VIX
    try:
        vix_values = fetch_closes(
            ".VIX"
        )

        vix = round(
            vix_values[-1],
            2,
        )

    except Exception as error:
        vix = previous.get(
            "vix"
        )

        errors.append(
            "VIX 조회 실패: "
            + repr(error)
        )

    # 나스닥100
    try:
        ndx_values = fetch_closes(
            ".NDX"
        )

        last = ndx_values[-1]

        ma200 = (
            sum(ndx_values[-200:])
            / 200
        )

        high_52w = max(
            ndx_values[-252:]
        )

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
            "days": len(
                ndx_values
            ),
        }

    except Exception as error:
        ndx = previous.get(
            "ndx"
        )

        errors.append(
            "나스닥100 조회 실패: "
            + repr(error)
        )

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
