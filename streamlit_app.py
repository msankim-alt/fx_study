"""
FX Monitor — Streamlit Community Cloud 배포 버전
"""
import os, sys, sqlite3
import streamlit as st
import requests
import plotly.graph_objects as go
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FX Monitor 환율 모니터",
    page_icon="💱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 자동 갱신 (1분) ──────────────────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60_000, key="fx_autorefresh")
except ImportError:
    pass

# ── Groq API Key (Streamlit Secrets 우선) ────────────────────────────────────
def get_groq_key() -> str:
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.getenv("GROQ_API_KEY", "")

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .rate-card {
    border: 1.5px solid #e2e8f0; border-radius: 12px;
    padding: 20px 16px; text-align: center;
    border-top-width: 4px; margin-bottom: 8px;
  }
  .card-usd { border-top-color: #3b82f6; }
  .card-eur { border-top-color: #10b981; }
  .card-dxy { border-top-color: #7c3aed; }
  .rate-label { font-size: 12px; color: #64748b; font-weight: 600; letter-spacing:.5px; }
  .rate-value { font-size: 30px; font-weight: 700; margin: 8px 0 4px; }
  .badge-row  { display:flex; justify-content:center; gap:6px; flex-wrap:wrap; margin:4px 0; }
  .badge { padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .up   { background:#fef2f2; color:#ef4444; }
  .down { background:#eff6ff; color:#3b82f6; }
  .flat { background:#f1f5f9; color:#64748b; }
  .rate-sub { font-size:11px; color:#94a3b8; margin-top:4px; }
  .rate-hl  { font-size:11px; color:#94a3b8; margin-top:4px; }
  .stat-row { display:flex; gap:10px; flex-wrap:wrap; }
  .stat-box { flex:1; min-width:120px; background:#f8fafc; border-radius:8px; padding:12px 14px; text-align:center; }
  .stat-label { font-size:11px; color:#64748b; }
  .stat-value { font-size:16px; font-weight:700; margin-top:4px; }
  .stat-date  { font-size:11px; color:#94a3b8; margin-top:2px; }
</style>
""", unsafe_allow_html=True)

# ── Yahoo Finance 공통 헤더 ──────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

# ── 데이터 수집 함수 ─────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_rates():
    result = {}
    for cur, sym in {"USD": "USDKRW=X", "EUR": "EURKRW=X"}.items():
        for host in ["query1", "query2"]:
            try:
                r = requests.get(
                    f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"interval": "1m", "range": "1d"},
                    headers=_HEADERS, timeout=8,
                )
                if r.status_code != 200:
                    continue
                meta = r.json()["chart"]["result"][0]["meta"]
                result[cur] = {
                    "current": round(meta["regularMarketPrice"], 1),
                    "prev":    round(meta.get("previousClose", meta["regularMarketPrice"]), 1),
                    "high":    round(meta.get("regularMarketDayHigh", 0), 1),
                    "low":     round(meta.get("regularMarketDayLow",  0), 1),
                }
                break
            except Exception:
                continue
    return result


@st.cache_data(ttl=60)
def fetch_dxy():
    for host in ["query1", "query2"]:
        try:
            r = requests.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
                params={"interval": "1d", "range": "10d"},
                headers=_HEADERS, timeout=8,
            )
            if r.status_code != 200:
                continue
            res  = r.json()["chart"]["result"][0]
            meta = res["meta"]
            closes = [c for c in res["indicators"]["quote"][0].get("close", []) if c]
            current = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
            if not current:
                continue
            return {
                "current": round(current, 1),
                "prev":    round(closes[-2], 1) if len(closes) >= 2 else None,
                "high":    round(meta.get("fiftyTwoWeekHigh") or 0, 1),
                "low":     round(meta.get("fiftyTwoWeekLow")  or 0, 1),
            }
        except Exception:
            continue
    return None


@st.cache_data(ttl=3600)
def fetch_history():
    today = date.today()
    m = today.month - 3
    y = today.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    start = f"{y}-{m:02d}-01"
    try:
        r = requests.get(
            f"https://api.frankfurter.app/{start}..{today.isoformat()}",
            params={"from": "USD", "to": "KRW,EUR"}, timeout=10,
        )
        r.raise_for_status()
        raw = r.json()
        usd, eur = [], []
        for ds in sorted(raw.get("rates", {})):
            rates = raw["rates"][ds]
            krw, e = rates.get("KRW"), rates.get("EUR")
            if krw:
                usd.append({"date": ds, "rate": round(krw, 1)})
            if krw and e:
                eur.append({"date": ds, "rate": round(krw / e, 1)})
        return {"USD": usd, "EUR": eur}
    except Exception as e:
        return {"USD": [], "EUR": [], "error": str(e)}


# ── 환율 카드 HTML ────────────────────────────────────────────────────────────
def rate_card(label, css_class, value, prev, high, low, unit="원", decimals=1):
    if prev and prev > 0:
        chg_pct = (value - prev) / prev * 100
        chg_amt = value - prev
    else:
        chg_pct = chg_amt = 0.0

    dir_cls = "up" if chg_pct > 0.001 else "down" if chg_pct < -0.001 else "flat"
    arrow   = "▲" if dir_cls == "up" else "▼" if dir_cls == "down" else "—"
    sign    = "+" if chg_pct >= 0 else ""
    asign   = "+" if chg_amt >= 0 else ""

    fmt = f",.{decimals}f"
    val_str  = f"{value:{fmt}}"
    prev_str = f"{prev:{fmt}}" if prev else "—"
    high_str = f"{high:{fmt}}" if high else "—"
    low_str  = f"{low:{fmt}}"  if low  else "—"
    amt_str  = f"{asign}{chg_amt:{fmt}}{unit}"

    return f"""
<div class="rate-card {css_class}">
  <div class="rate-label">{label}</div>
  <div class="rate-value">{val_str}<span style="font-size:14px;color:#94a3b8"> {unit}</span></div>
  <div class="badge-row">
    <span class="badge {dir_cls}">{arrow} {sign}{chg_pct:.3f}%</span>
    <span class="badge {dir_cls}">{amt_str}</span>
  </div>
  <div class="rate-sub">기준: {prev_str}{unit}</div>
  <div class="rate-hl">고가 {high_str} · 저가 {low_str}</div>
</div>
"""


# ── DB 경로 ──────────────────────────────────────────────────────────────────
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fx_monitor.db")


def db_summaries(limit=24):
    if not os.path.exists(_DB):
        return []
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT hour_label, summary, created_at FROM news_summaries "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return [{"hour_label": r[0], "summary": r[1], "created_at": r[2]} for r in rows]
    except Exception:
        return []


def db_articles(limit=50):
    if not os.path.exists(_DB):
        return []
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT title, link, published, source_feed, collected_at "
            "FROM yonhap_articles ORDER BY collected_at DESC LIMIT ?", (limit,)
        ).fetchall()
        con.close()
        return rows
    except Exception:
        return []


# ── Session State ────────────────────────────────────────────────────────────
if "rate_history" not in st.session_state:
    st.session_state.rate_history = []


# ── 헤더 ─────────────────────────────────────────────────────────────────────
st.title("💱 FX Monitor 환율 모니터")
st.caption(f"마지막 갱신: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ·  1분 자동 갱신")

tab1, tab2, tab3, tab4 = st.tabs(["📊 환율 현황", "📰 연합뉴스 요약", "📋 수집 기사", "⚙️ 설정"])


# ════════════════════════════════════════════════════════════════════════════
# Tab 1 — 환율 현황
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    fx  = fetch_rates()
    dxy = fetch_dxy()

    if not fx:
        st.error("환율 수집에 실패했습니다. 잠시 후 다시 시도해주세요.")
        st.stop()

    usd = fx.get("USD", {})
    eur = fx.get("EUR", {})

    # 환율 카드
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(rate_card("🇺🇸 USD / KRW", "card-usd",
            usd["current"], usd["prev"], usd["high"], usd["low"]), unsafe_allow_html=True)
    with c2:
        st.markdown(rate_card("🇪🇺 EUR / KRW", "card-eur",
            eur["current"], eur["prev"], eur["high"], eur["low"]), unsafe_allow_html=True)
    with c3:
        if dxy:
            st.markdown(rate_card("📈 Dollar Index (DXY)", "card-dxy",
                dxy["current"], dxy["prev"], dxy["high"], dxy["low"],
                unit="", decimals=1), unsafe_allow_html=True)
        else:
            st.warning("DXY 수집 실패")

    # 당일 이력에 추가
    rec = {"ts": datetime.now().strftime("%H:%M"), "USD": usd.get("current"), "EUR": eur.get("current")}
    h = st.session_state.rate_history
    if not h or h[-1].get("USD") != rec["USD"] or h[-1].get("EUR") != rec["EUR"]:
        h.append(rec)
        if len(h) > 100:
            st.session_state.rate_history = h[-100:]

    # 당일 환율 추이 차트
    if len(st.session_state.rate_history) >= 2:
        st.subheader("📈 당일 환율 추이")
        mode = st.radio("표시", ["전체", "USD/KRW", "EUR/KRW"], horizontal=True, key="intraday_mode")
        hist = st.session_state.rate_history
        times = [h["ts"] for h in hist]
        fig = go.Figure()
        if mode in ("전체", "USD/KRW"):
            fig.add_trace(go.Scatter(x=times, y=[h.get("USD") for h in hist],
                name="USD/KRW", line=dict(color="#3b82f6", width=2),
                hovertemplate="%{y:,.1f}원<extra>USD/KRW</extra>"))
        if mode in ("전체", "EUR/KRW"):
            fig.add_trace(go.Scatter(x=times, y=[h.get("EUR") for h in hist],
                name="EUR/KRW", line=dict(color="#10b981", width=2),
                yaxis="y2" if mode == "전체" else "y",
                hovertemplate="%{y:,.1f}원<extra>EUR/KRW</extra>"))
        fig.update_layout(
            height=260, margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=1.12),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
            yaxis2=dict(overlaying="y", side="right", showgrid=False) if mode == "전체" else {},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    # 3개월 이력 차트
    st.subheader("📅 3개월 환율 추이")
    hist3 = fetch_history()

    if hist3.get("USD") or hist3.get("EUR"):
        fig2 = go.Figure()
        if hist3.get("USD"):
            fig2.add_trace(go.Scatter(
                x=[d["date"] for d in hist3["USD"]], y=[d["rate"] for d in hist3["USD"]],
                name="USD/KRW", line=dict(color="#3b82f6", width=2),
                hovertemplate="%{x}<br>%{y:,.1f}원<extra>USD/KRW</extra>"))
        if hist3.get("EUR"):
            fig2.add_trace(go.Scatter(
                x=[d["date"] for d in hist3["EUR"]], y=[d["rate"] for d in hist3["EUR"]],
                name="EUR/KRW", line=dict(color="#10b981", width=2), yaxis="y2",
                hovertemplate="%{x}<br>%{y:,.1f}원<extra>EUR/KRW</extra>"))
        fig2.update_layout(
            height=300, margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=1.12),
            xaxis=dict(showgrid=False, tickangle=-30),
            yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
            yaxis2=dict(overlaying="y", side="right", showgrid=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

        # 3개월 통계
        st.subheader("📊 3개월 통계")
        sc1, sc2 = st.columns(2)
        for label, series, col in [("USD/KRW", hist3.get("USD", []), sc1),
                                     ("EUR/KRW", hist3.get("EUR", []), sc2)]:
            if not series:
                continue
            rates = [d["rate"] for d in series]
            max_r, min_r = max(rates), min(rates)
            avg_r = sum(rates) / len(rates)
            max_d = next(d["date"] for d in series if d["rate"] == max_r)
            min_d = next(d["date"] for d in series if d["rate"] == min_r)
            with col:
                st.markdown(f"**{label}**")
                st.markdown(f"""
<div class="stat-row">
  <div class="stat-box">
    <div class="stat-label">🔴 최고가</div>
    <div class="stat-value">{max_r:,.1f}원</div>
    <div class="stat-date">{max_d}</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">🔵 최저가</div>
    <div class="stat-value">{min_r:,.1f}원</div>
    <div class="stat-date">{min_d}</div>
  </div>
  <div class="stat-box">
    <div class="stat-label">📊 누계 평균</div>
    <div class="stat-value">{avg_r:,.1f}원</div>
    <div class="stat-date">&nbsp;</div>
  </div>
</div>
""", unsafe_allow_html=True)
    else:
        if "error" in hist3:
            st.warning(f"3개월 데이터 수집 실패: {hist3['error']}")


# ════════════════════════════════════════════════════════════════════════════
# Tab 2 — 연합뉴스 요약
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("📰 연합뉴스 · 인포맥스 환율 기사 요약")

    btn_col, info_col = st.columns([1, 4])
    with btn_col:
        do_collect = st.button("🔄 지금 수집·요약", use_container_width=True)
    with info_col:
        st.caption("Groq AI (llama-3.3-70b)로 요약합니다. 약 30~60초 소요됩니다.")

    if do_collect:
        groq_key = get_groq_key()
        if not groq_key:
            st.error("❌ GROQ_API_KEY가 설정되지 않았습니다. '설정' 탭을 확인해주세요.")
        else:
            os.environ["GROQ_API_KEY"] = groq_key
            with st.spinner("뉴스 수집 및 AI 요약 중..."):
                try:
                    from yonhap_news import init_news_db, run_news_pipeline
                    init_news_db()
                    summary = run_news_pipeline()
                    st.session_state["latest_summary"] = {
                        "hour_label": datetime.now().strftime("%Y년 %m월 %d일 %H시"),
                        "summary": summary,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    st.success("✅ 수집 완료!")
                except Exception as e:
                    st.error(f"오류: {e}")

    # 요약 목록 (세션 + DB)
    summaries = []
    if "latest_summary" in st.session_state:
        summaries.append(st.session_state["latest_summary"])

    seen = {s["hour_label"] for s in summaries}
    for s in db_summaries():
        if s["hour_label"] not in seen:
            summaries.append(s)
            seen.add(s["hour_label"])

    if summaries:
        for i, s in enumerate(summaries):
            with st.expander(f"📌 {s['hour_label']}  ·  {s.get('created_at', '')}", expanded=(i == 0)):
                st.markdown(s["summary"])
    else:
        st.info("아직 요약이 없습니다. '지금 수집·요약' 버튼을 눌러주세요.")


# ════════════════════════════════════════════════════════════════════════════
# Tab 3 — 수집 기사
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("📋 수집 기사 목록")
    articles = db_articles()
    if articles:
        for title, link, published, source, collected in articles:
            st.markdown(f"**[{title}]({link})**")
            st.caption(f"{source}  ·  {published}  ·  수집: {collected}")
            st.divider()
    else:
        st.info("수집된 기사가 없습니다. '연합뉴스 요약' 탭에서 수집을 시작해주세요.")


# ════════════════════════════════════════════════════════════════════════════
# Tab 4 — 설정
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("⚙️ 설정")

    # API 키 상태
    groq_key = get_groq_key()
    if groq_key:
        masked = groq_key[:8] + "****" + groq_key[-4:]
        st.success(f"✅ Groq API 키 설정됨: `{masked}`")
        if st.button("🧪 연결 테스트"):
            with st.spinner("테스트 중..."):
                try:
                    from groq import Groq
                    client = Groq(api_key=groq_key)
                    res = client.chat.completions.create(
                        model="llama-3.3-70b-versatile", max_tokens=20,
                        messages=[{"role": "user", "content": "환율을 한 단어로 표현하면?"}]
                    )
                    st.success(f"✅ 연결 성공! 응답: {res.choices[0].message.content.strip()}")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {e}")
    else:
        st.error("❌ Groq API 키가 설정되지 않았습니다.")

    st.divider()
    st.subheader("📊 시스템 정보")
    ic1, ic2 = st.columns(2)
    with ic1:
        st.markdown("- **수집 통화:** USD/KRW · EUR/KRW")
        st.markdown("- **환율 소스:** Yahoo Finance (실시간)")
        st.markdown("- **이력 소스:** Frankfurter API (3개월)")
    with ic2:
        st.markdown("- **뉴스 소스:** 연합뉴스 · 연합인포맥스")
        st.markdown("- **AI 모델:** Groq llama-3.3-70b-versatile")
        st.markdown("- **갱신 주기:** 1분 자동 갱신")
