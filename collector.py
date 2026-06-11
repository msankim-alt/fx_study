import requests
import feedparser
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def fetch_exchange_rates() -> dict:
    """한국수출입은행 API로 USD·EUR 환율 수집 (엔화 제외)"""
    url = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
    params = {
        "authkey": os.getenv("KOREAEXIM_API_KEY"),
        "searchdate": datetime.now().strftime("%Y%m%d"),
        "data": "AP01"
    }
    try:
        res = requests.get(url, params=params, timeout=10).json()
        targets = {"USD": None, "EUR": None}   # JPY 제외
        for item in res:
            if item["cur_unit"] in targets:
                targets[item["cur_unit"]] = float(item["deal_bas_r"].replace(",", ""))
        return targets
    except Exception as e:
        print(f"[ERROR] 환율 수집 실패: {e}")
        return {}


def fetch_news(query: str = "환율 달러 원화", display: int = 10) -> list:
    """Naver 뉴스 API로 환율 관련 뉴스 수집"""
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
        "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET")
    }
    params = {"query": query, "display": display, "sort": "date"}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10).json()
        return [
            {
                "title": item["title"].replace("<b>", "").replace("</b>", ""),
                "desc": item["description"].replace("<b>", "").replace("</b>", ""),
                "link": item["link"],
                "pub_date": item["pubDate"]
            }
            for item in res.get("items", [])
        ]
    except Exception as e:
        print(f"[ERROR] 뉴스 수집 실패: {e}")
        return []


RSS_FEEDS = {
    "한국은행": "https://www.bok.or.kr/portal/bbs/B0000338/list.do?menuNo=200761&feed=Y",
    "기획재정부": "https://www.moef.go.kr/nw/nes/detailNesDtaView.do?feed=Y"
}


def fetch_rss() -> list:
    """한국은행·기획재정부 RSS 피드 수집"""
    articles = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                articles.append({
                    "source": source,
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", "")
                })
        except Exception as e:
            print(f"[ERROR] RSS 수집 실패 ({source}): {e}")
    return articles
