"""中国银行外汇牌价抓取 (v2)。"""
import requests
from bs4 import BeautifulSoup

URL = "https://www.boc.cn/sourcedb/whpj/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15
MAX_RETRIES = 3

# 货币中文名 → 代码
CURRENCY_CODE = {
    "美元": "USD", "英镑": "GBP", "欧元": "EUR", "日元": "JPY",
    "港币": "HKD", "澳大利亚元": "AUD", "加拿大元": "CAD", "瑞士法郎": "CHF",
    "新加坡元": "SGD", "新西兰元": "NZD", "丹麦克朗": "DKK", "挪威克朗": "NOK",
    "瑞典克朗": "SEK", "澳门元": "MOP", "泰铢": "THB", "韩元": "KRW",
    "卢布": "RUB", "马来西亚林吉特": "MYR", "菲律宾比索": "PHP", "印尼卢比": "IDR",
}

# 默认目录名称（展示用）
CNY_LABEL = "人民币"


def fetch_rate_rows():
    """抓回中行外汇牌价表，返回按币种名的行字典。

    行字段（中行 whpj 表 tds 顺序）：
    0 货币名称, 1 现汇买入价, 2 现钞买入价, 3 现汇卖出价,
    4 现钞卖出价, 5 中行折算价, 6 发布时间, ...
    中行的价格都是「每 100 外币兑人民币」。
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = {}
            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 7:
                    continue
                name = tds[0].get_text().strip()
                if name in CURRENCY_CODE:
                    def _p(i):
                        try:
                            return float(tds[i].get_text().strip())
                        except Exception:
                            return None

                    rows[name] = {
                        "name": name,
                        "code": CURRENCY_CODE[name],
                        "buy_spot": _p(1),      # 现汇买入
                        "buy_cash": _p(2),      # 现钞买入
                        "sell_spot": _p(3),     # 现汇卖出
                        "sell_cash": _p(4),     # 现钞卖出
                        "middle": _p(5),        # 中行折算
                        "time": tds[6].get_text().strip(),
                    }
            if rows:
                return rows
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < MAX_RETRIES - 1:
                continue
            return None
        except Exception:
            return None
    return None


def rate_for_1_cny(raw_per_100):
    """每 100 外币兑人民币 → 1 外币兑人民币，4 位小数。"""
    try:
        return "{:.4f}".format(float(raw_per_100) / 100.0)
    except Exception:
        return None


def build_pairs(rows):
    """把抓到的行转成前端 pair 列表（1 外币兑人民币）。"""
    pairs = []
    order = ["美元", "英镑", "欧元", "日元", "港币", "澳大利亚元", "加拿大元",
             "瑞士法郎", "新加坡元", "新西兰元", "丹麦克朗", "挪威克朗",
             "瑞典克朗", "澳门元", "泰铢", "韩元", "卢布", "马来西亚林吉特",
             "菲律宾比索", "印尼卢比"]
    for name in order:
        row = rows.get(name)
        if not row:
            continue
        buy = rate_for_1_cny(row["buy_spot"])
        if not buy:
            continue
        pairs.append({
            "code": row["code"] + "/CNY",
            "name": row["name"],
            "rate": buy,
            "sellRate": rate_for_1_cny(row["sell_spot"]),
            "cashRate": rate_for_1_cny(row["buy_cash"]),
            "cashSellRate": rate_for_1_cny(row["sell_cash"]),
            "middle": rate_for_1_cny(row["middle"]),
            "time": row["time"],
        })
    return pairs