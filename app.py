"""
Flask 웹 서버 — 환율 대시보드 + 뉴스 요약 API
실행: python app.py
접속: http://localhost:5000
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

DB_PATH = "data/fx_monitor.db"

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ── 정적 파일 ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ── 뉴스 요약 API ──────────────────────────────────────────────────────

@app.route("/api/summaries")
def api_summaries():
    """최근 24시간 요약 목록"""
    limit = int(request.args.get("limit", 24))
    try:
        con = get_db()
        rows = con.execute(
            "SELECT hour_label, summary, created_at FROM news_summaries "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/summaries/latest")
def api_latest_summary():
    """가장 최근 요약"""
    try:
        con = get_db()
        row = con.execute(
            "SELECT hour_label, summary, created_at FROM news_summaries "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        con.close()
        if row:
            return jsonify(dict(row))
        return jsonify({"summary": "아직 수집된 요약이 없습니다. news_scheduler.py를 실행해주세요."})
    except Exception:
        return jsonify({"summary": "DB를 찾을 수 없습니다. news_scheduler.py를 먼저 실행해주세요."})


@app.route("/api/articles")
def api_articles():
    """최근 기사 목록 (본문 제외)"""
    limit = int(request.args.get("limit", 50))
    try:
        con = get_db()
        rows = con.execute(
            "SELECT article_id, title, link, published, source_feed, collected_at "
            "FROM yonhap_articles ORDER BY collected_at DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/articles/count")
def api_article_count():
    """시간대별 기사 수"""
    try:
        con = get_db()
        rows = con.execute(
            "SELECT strftime('%Y-%m-%d %H', collected_at) as hour, COUNT(*) as cnt "
            "FROM yonhap_articles GROUP BY hour ORDER BY hour DESC LIMIT 24"
        ).fetchall()
        con.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 환율 이력 API ──────────────────────────────────────────────────────

@app.route("/api/rates/history")
def api_rates_history():
    """최근 환율 이력"""
    limit = int(request.args.get("limit", 60))
    try:
        con = get_db()
        rows = con.execute(
            "SELECT timestamp, usd_krw, jpy_krw, eur_krw FROM exchange_rates "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return jsonify([dict(r) for r in reversed(rows)])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DXY 달러 인덱스 ────────────────────────────────────────────────────

def _yahoo_dxy():
    """Yahoo Finance에서 DXY 수집 (query1 → query2 순서로 시도)"""
    import requests as req
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    for host in ["query1", "query2"]:
        try:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
            r = req.get(url, params={"interval": "1d", "range": "10d"},
                        headers=headers, timeout=8)
            if r.status_code != 200:
                continue
            data = r.json()
            result = data["chart"]["result"][0]
            meta   = result["meta"]
            q      = result["indicators"]["quote"][0]
            closes = [c for c in q.get("close", []) if c is not None]
            highs  = [h for h in q.get("high",  []) if h is not None]
            lows   = [l for l in q.get("low",   []) if l is not None]

            current = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
            prev    = closes[-2] if len(closes) >= 2 else None
            high52  = meta.get("fiftyTwoWeekHigh") or (max(highs) if highs else None)
            low52   = meta.get("fiftyTwoWeekLow")  or (min(lows)  if lows  else None)

            if current is None:
                continue
            return {
                "current": round(current, 3),
                "prev":    round(prev,    3) if prev   else None,
                "high":    round(high52,  3) if high52 else None,
                "low":     round(low52,   3) if low52  else None,
            }
        except Exception:
            continue
    return None


@app.route("/api/rates")
def api_rates():
    """Yahoo Finance에서 USD/KRW · EUR/KRW 실시간 환율 수집"""
    import requests as req
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    result = {}
    symbols = {"USD": "USDKRW=X", "EUR": "EURKRW=X"}
    for cur, sym in symbols.items():
        for host in ["query1", "query2"]:
            try:
                url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
                r = req.get(url, params={"interval": "1m", "range": "1d"},
                            headers=headers, timeout=8)
                if r.status_code != 200:
                    continue
                d = r.json()["chart"]["result"][0]
                meta = d["meta"]
                result[cur] = {
                    "current": round(meta["regularMarketPrice"], 2),
                    "prev":    round(meta.get("previousClose", meta["regularMarketPrice"]), 2),
                    "high":    round(meta.get("regularMarketDayHigh", 0), 2),
                    "low":     round(meta.get("regularMarketDayLow",  0), 2),
                }
                break
            except Exception:
                continue

    if not result:
        return jsonify({"error": "환율 수집 실패"}), 500
    return jsonify(result)


@app.route("/api/dxy")
def api_dxy():
    data = _yahoo_dxy()
    if data:
        return jsonify(data)
    return jsonify({"error": "DXY 수집 실패"}), 500


@app.route("/api/history")
def api_history():
    """Frankfurter API로 3개월 일별 USD·EUR/KRW 환율 서버사이드 수집"""
    import requests as req
    from datetime import date
    today = date.today()
    # 3개월 전 1일
    month3 = today.month - 3
    year3  = today.year + (month3 - 1) // 12
    month3 = ((month3 - 1) % 12) + 1
    start  = f"{year3}-{month3:02d}-01"
    end    = today.isoformat()

    try:
        url = f"https://api.frankfurter.app/{start}..{end}"
        r = req.get(url, params={"from": "USD", "to": "KRW,EUR"}, timeout=10)
        r.raise_for_status()
        raw = r.json()

        usd_series, eur_series = [], []
        for date_str in sorted(raw.get("rates", {})):
            rates = raw["rates"][date_str]
            krw = rates.get("KRW")
            eur = rates.get("EUR")
            if krw:
                usd_series.append({"date": date_str, "rate": round(krw, 2)})
            if krw and eur:
                eur_series.append({"date": date_str, "rate": round(krw / eur, 2)})

        return jsonify({"start": start, "end": end,
                        "USD": usd_series, "EUR": eur_series})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API 키 설정 ────────────────────────────────────────────────────────

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

def read_env_dict():
    """현재 .env 파일을 key=value dict로 읽기"""
    result = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip()
    return result

def write_env_dict(d: dict):
    """dict를 .env 파일에 덮어쓰기"""
    lines = []
    # 기존 파일의 주석과 빈줄 유지하면서 값만 교체
    existing = {}
    file_lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            file_lines = f.readlines()

    written_keys = set()
    new_lines = []
    for line in file_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            k = k.strip()
            if k in d:
                new_lines.append(f"{k}={d[k]}\n")
                written_keys.add(k)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # 새로 추가된 키 append
    for k, v in d.items():
        if k not in written_keys:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


@app.route("/api/settings/apikey", methods=["GET"])
def get_apikey():
    """현재 API 키 마스킹 정보 반환"""
    env = read_env_dict()
    key = env.get("GROQ_API_KEY", "")
    if key and len(key) > 12:
        masked = key[:8] + "****" + key[-4:]
        return jsonify({"has_key": True, "masked": masked})
    return jsonify({"has_key": False, "masked": ""})


@app.route("/api/settings/apikey", methods=["POST"])
def save_apikey():
    """API 키를 .env에 저장"""
    data = request.get_json()
    key = (data or {}).get("groq_api_key", "").strip()
    if not key:
        return jsonify({"status": "error", "message": "키가 비어있습니다."}), 400
    try:
        env = read_env_dict()
        env["GROQ_API_KEY"] = key
        write_env_dict(env)
        os.environ["GROQ_API_KEY"] = key
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/settings/test")
def test_apikey():
    """Groq API 연결 테스트"""
    from groq import Groq
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return jsonify({"status": "error", "message": "API 키가 설정되지 않았습니다."})
    try:
        client = Groq(api_key=key)
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=20,
            messages=[{"role": "user", "content": "환율을 한 단어로 표현하면?"}]
        )
        reply = res.choices[0].message.content.strip()
        return jsonify({"status": "ok", "model": "llama-3.3-70b-versatile", "reply": reply})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ── 수동 트리거 ────────────────────────────────────────────────────────

@app.route("/api/collect", methods=["POST"])
def api_collect():
    """뉴스 수집 즉시 실행 (수동 트리거)"""
    try:
        from yonhap_news import init_news_db, run_news_pipeline
        init_news_db()
        summary = run_news_pipeline()
        return jsonify({"status": "ok", "summary": summary or "완료"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    print("=" * 50)
    print("  FX Monitor 웹 서버 시작")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
