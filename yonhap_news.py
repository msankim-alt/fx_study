"""
연합뉴스 환율 관련 기사 수집 + Groq 요약 모듈
"""

import requests
import feedparser
import sqlite3
import json
import os
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

DB_PATH = "data/fx_monitor.db"

YONHAP_RSS_FEEDS = {
    "경제일반":          "https://www.yna.co.kr/rss/economy.xml",
    "금융·증권":         "https://www.yna.co.kr/rss/finance.xml",
    "외환·통화":         "https://www.yna.co.kr/rss/international.xml",
    "인포맥스_외환금리": "https://news.einfomax.co.kr/rss/S1N2.xml",
    "인포맥스_전체":     "https://news.einfomax.co.kr/rss/allArticle.xml",
}

FX_KEYWORDS = [
    "환율", "달러", "원화", "원/달러", "외환", "엔화", "유로화", "위안화",
    "강달러", "약달러", "환시", "외환시장", "달러인덱스", "USD", "JPY", "EUR",
    "원달러", "통화", "외화", "환전", "기준금리", "연준", "Fed", "금리",
    "무역수지", "경상수지", "외국인 자금", "자본유출", "자본유입"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _safe_print(msg):
    try:
        print(msg)
    except Exception:
        pass


# ── DB 초기화 ──────────────────────────────────────────────────────────

def init_news_db():
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS yonhap_articles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id  TEXT UNIQUE,
            title       TEXT,
            link        TEXT,
            published   TEXT,
            source_feed TEXT,
            body        TEXT,
            collected_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_summaries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            hour_label   TEXT UNIQUE,
            article_ids  TEXT,
            summary      TEXT,
            created_at   TEXT
        )
    """)
    con.commit()
    con.close()


# ── RSS 수집 ───────────────────────────────────────────────────────────

def _is_fx_related(title: str, summary: str = "") -> bool:
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in FX_KEYWORDS)


def fetch_yonhap_rss() -> list:
    articles = []
    seen_ids = set()

    for feed_name, url in YONHAP_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url, request_headers=HEADERS)
            for entry in feed.entries:
                title   = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                link    = entry.get("link", "").strip()
                pub     = entry.get("published", entry.get("updated", ""))

                if not _is_fx_related(title, summary):
                    continue

                match = re.search(r"/(\d{10,})", link)
                article_id = match.group(1) if match else link[-20:]

                if article_id in seen_ids:
                    continue
                seen_ids.add(article_id)

                articles.append({
                    "article_id":  article_id,
                    "title":       title,
                    "link":        link,
                    "published":   pub,
                    "source_feed": feed_name,
                    "summary":     summary,
                })

            _safe_print(f"[INFO] RSS '{feed_name}': {sum(1 for a in articles if a['source_feed']==feed_name)}건")
            time.sleep(0.5)

        except Exception as e:
            _safe_print(f"[ERROR] RSS 수집 실패 ({feed_name}): {e}")

    return articles


# ── 본문 스크래핑 ──────────────────────────────────────────────────────

def scrape_article_body(url: str) -> str:
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        if "einfomax" in url:
            for sel in ["div.view-content", "div#article_content", "div.article_body", "div.view_content"]:
                el = soup.select_one(sel)
                if el:
                    for tag in el.select("script, style, .ad, figure"):
                        tag.decompose()
                    text = el.get_text(separator="\n").strip()
                    if len(text) > 100:
                        return text[:3000]

        for sel in ["div.article-txt", "div.story-news article", "article.story-news",
                    "div#articleWrap", "div.content article"]:
            el = soup.select_one(sel)
            if el:
                for tag in el.select("script, style, .article-ad, .promotion"):
                    tag.decompose()
                text = el.get_text(separator="\n").strip()
                if len(text) > 100:
                    return text[:3000]

        paragraphs = [p.get_text().strip() for p in soup.select("p") if len(p.get_text().strip()) > 30]
        return "\n".join(paragraphs[:20])[:3000]

    except Exception as e:
        _safe_print(f"[WARN] 본문 스크래핑 실패 ({url}): {e}")
        return ""


# ── DB 저장 ────────────────────────────────────────────────────────────

def save_articles(articles: list) -> list:
    con = sqlite3.connect(DB_PATH)
    saved = []
    for a in articles:
        try:
            con.execute(
                """INSERT OR IGNORE INTO yonhap_articles
                   (article_id, title, link, published, source_feed, body, collected_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (a["article_id"], a["title"], a["link"], a["published"],
                 a["source_feed"], a.get("body", ""), datetime.now().isoformat())
            )
            if con.execute("SELECT changes()").fetchone()[0]:
                saved.append(a)
        except Exception as e:
            _safe_print(f"[WARN] 저장 실패: {e}")
    con.commit()
    con.close()
    return saved


def get_articles_for_hour(hour_label: str = None) -> list:
    if hour_label is None:
        hour_label = datetime.now().strftime("%Y-%m-%d %H")
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT article_id, title, link, published, body FROM yonhap_articles "
        "WHERE collected_at LIKE ? OR collected_at LIKE ? ORDER BY collected_at",
        (hour_label + "%", hour_label.replace(" ", "T") + "%")
    ).fetchall()
    con.close()
    return [
        {"article_id": r[0], "title": r[1], "link": r[2],
         "published": r[3], "body": r[4]}
        for r in rows
    ]


def get_recent_summaries(limit: int = 24) -> list:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT hour_label, summary, created_at FROM news_summaries "
        "ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [{"hour_label": r[0], "summary": r[1], "created_at": r[2]} for r in rows]


# ── Groq 요약 (requests 직접 호출) ────────────────────────────────────

def summarize_with_claude(articles: list) -> str:
    if not articles:
        return "이 시간대에 수집된 환율 관련 기사가 없습니다."

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "[오류] GROQ_API_KEY가 설정되지 않았습니다."

    articles_text = ""
    for i, a in enumerate(articles[:12], 1):
        body = a.get("body", "").strip() or "(본문 없음)"
        articles_text += f"\n[기사 {i}] {a['title']}\n출처: {a['link']}\n{body[:800]}\n"

    hour_label = datetime.now().strftime("%Y년 %m월 %d일 %H시")

    prompt = (
        f"당신은 외환·금융시장 전문 애널리스트입니다.\n"
        f"아래는 {hour_label} 기준 연합뉴스에서 수집된 환율 관련 기사 {len(articles)}건입니다.\n"
        f"\n{articles_text}\n"
        f"위 기사들을 바탕으로 다음 형식에 맞게 시간별 요약 리포트를 작성해주세요:\n\n"
        f"## {hour_label} 환율 뉴스 요약\n\n"
        f"### 핵심 동향 (3줄 요약)\n-\n-\n-\n\n"
        f"### 주요 기사 분석\n(각 기사의 핵심 내용을 2~3문장으로 정리)\n\n"
        f"### 환율 영향 요인\n**상승 요인 (원화 약세):**\n-\n\n**하락 요인 (원화 강세):**\n-\n\n"
        f"### 시장 주목 포인트\n(투자자·트레이더가 주의해야 할 사항)\n\n"
        f"간결하고 전문적으로 작성하되, 구체적인 수치나 사실이 있으면 반드시 포함해주세요."
    )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        import traceback
        return f"[AI 요약 오류] {e}\n\n{traceback.format_exc()}"


def save_summary(hour_label: str, article_ids: list, summary: str):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """INSERT INTO news_summaries (hour_label, article_ids, summary, created_at)
           VALUES (?,?,?,?)
           ON CONFLICT(hour_label) DO UPDATE SET
             article_ids=excluded.article_ids,
             summary=excluded.summary,
             created_at=excluded.created_at""",
        (hour_label, json.dumps(article_ids), summary, datetime.now().isoformat())
    )
    con.commit()
    con.close()


# ── 메인 파이프라인 ────────────────────────────────────────────────────

def run_news_pipeline():
    hour_label = datetime.now().strftime("%Y-%m-%d %H")
    _safe_print(f"[{datetime.now().strftime('%H:%M:%S')}] 연합뉴스 수집 시작 ({hour_label})")

    articles = fetch_yonhap_rss()
    _safe_print(f"[INFO] 환율 관련 기사 {len(articles)}건 발견")

    if not articles:
        return "수집된 기사가 없습니다."

    con = sqlite3.connect(DB_PATH)
    existing_ids = {r[0] for r in con.execute("SELECT article_id FROM yonhap_articles").fetchall()}
    con.close()

    new_articles = [a for a in articles if a["article_id"] not in existing_ids]
    _safe_print(f"[INFO] 신규 기사 {len(new_articles)}건 본문 수집 중...")

    for a in new_articles:
        if a["link"]:
            a["body"] = scrape_article_body(a["link"])
            time.sleep(0.8)

    saved = save_articles(new_articles)
    _safe_print(f"[INFO] {len(saved)}건 저장 완료")

    hour_articles = get_articles_for_hour(hour_label)
    _safe_print(f"[INFO] {len(hour_articles)}건으로 요약 생성 중...")

    summary = summarize_with_claude(hour_articles)

    article_ids = [a["article_id"] for a in hour_articles]
    save_summary(hour_label, article_ids, summary)

    _safe_print(f"[OK] 요약 저장 완료 (hour={hour_label})")
    return summary


if __name__ == "__main__":
    init_news_db()
    run_news_pipeline()
