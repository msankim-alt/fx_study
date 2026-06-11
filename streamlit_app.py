"""
FX Monitor — Streamlit Community Cloud (index.html 스타일 적용)
"""
import os, sys, sqlite3
import streamlit as st
import requests
import plotly.graph_objects as go
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FX Monitor 환율 변동 모니터",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 자동 갱신 (1분) ──────────────────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60_000, key="fx_autorefresh")
except ImportError:
    pass

# ── Secrets ──────────────────────────────────────────────────────────────────
def get_groq_key() -> str:
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.getenv("GROQ_API_KEY", "")

# ── CSS (index.html 스타일 완전 적용) ────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700;800&display=swap');

/* Streamlit 기본 요소 제거 */
#MainMenu, footer, header[data-testid="stHeader"] { display:none !important; }
.stApp { background:#f8fafc !important; font-family:'Noto Sans KR',-apple-system,sans-serif; }
.block-container { padding:0 80px !important; max-width:100% !important; margin-top:56px !important; }

/* 탭 → index.html .page-tabs 스타일 */
.stTabs [data-baseweb="tab-list"] {
  gap:0; border-bottom:2px solid #e2e8f0;
  background:#fff; padding:0;
}
.stTabs [data-baseweb="tab"] {
  padding:12px 24px; font-size:14px; font-weight:600;
  color:#64748b; border-bottom:3px solid transparent;
  background:transparent; margin-bottom:-2px; white-space:nowrap;
}
.stTabs [aria-selected="true"] {
  color:#1d4ed8 !important; border-bottom:3px solid #1d4ed8 !important;
  background:transparent !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display:none; }
.stTabs [data-baseweb="tab-panel"]  { padding:0 !important; background:#f8fafc; }

/* radio → pill 탭처럼 */
div[data-testid="stHorizontalBlock"] .stRadio > div {
  display:flex; gap:8px; flex-wrap:wrap;
}
.stRadio [data-testid="stMarkdownContainer"] p { display:none; }
.stRadio label {
  padding:5px 14px !important; border-radius:20px !important;
  font-size:12px !important; font-weight:600 !important;
  border:1px solid #e2e8f0 !important; background:#f1f5f9 !important;
  color:#64748b !important; cursor:pointer !important;
}
.stRadio label[data-checked="true"],
.stRadio input:checked + div { background:#1d4ed8 !important; color:#fff !important; border-color:#1d4ed8 !important; }

/* 버튼 */
.stButton > button {
  background:#1d4ed8 !important; color:#fff !important;
  border:none !important; border-radius:8px !important;
  font-weight:600 !important; font-size:13px !important;
}
.stButton > button:hover { background:#1e3a8a !important; }

/* expander → 뉴스 카드 */
[data-testid="stExpander"] {
  border:none !important; border-radius:14px !important;
  overflow:hidden !important; margin-bottom:16px !important;
  box-shadow:0 1px 4px rgba(0,0,0,.08) !important;
  background:#fff !important;
}
.streamlit-expanderHeader {
  background:#1e3a8a !important; color:#fff !important;
  font-weight:700 !important; font-size:13px !important;
  border-radius:0 !important; padding:14px 20px !important;
}
.streamlit-expanderHeader p,
.streamlit-expanderHeader span { color:#fff !important; }
.streamlit-expanderHeader svg  { stroke:#fff !important; }

/* spinner */
.stSpinner > div { border-top-color:#1d4ed8 !important; }

/* info/success/error 메시지 */
.stAlert { border-radius:10px !important; }
</style>
""", unsafe_allow_html=True)

# ── 고정 헤더 ─────────────────────────────────────────────────────────────────
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"""
<header style="position:fixed;top:0;left:0;right:0;z-index:999;
  background:#1e3a8a;color:#fff;padding:0 32px;height:56px;
  display:flex;align-items:center;justify-content:space-between;
  box-shadow:0 2px 8px rgba(0,0,0,.2);font-family:'Noto Sans KR',sans-serif;">
  <h1 style="font-size:18px;font-weight:700;letter-spacing:-.3px;margin:0;">
    📊 FX Monitor
    <span style="opacity:.6;font-weight:400;font-size:13px;margin-left:10px;">환율 변동 모니터</span>
  </h1>
  <div style="display:flex;align-items:center;gap:16px;">
    <div style="display:flex;align-items:center;gap:6px;font-size:12px;opacity:.85;">
      <div style="width:8px;height:8px;border-radius:50%;background:#4ade80;
        animation:pulse 2s infinite;"></div>
      <span>실시간</span>
    </div>
    <span style="font-size:12px;opacity:.6;">{now_str}</span>
  </div>
</header>
<style>@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}</style>
""", unsafe_allow_html=True)

# ── 데이터 수집 함수 ─────────────────────────────────────────────────────────
_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

@st.cache_data(ttl=60)
def fetch_rates():
    result = {}
    for cur, sym in {"USD": "USDKRW=X", "EUR": "EURKRW=X"}.items():
        for host in ["query1", "query2"]:
            try:
                r = requests.get(
                    f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"interval": "1m", "range": "1d"},
                    headers=_H, timeout=8)
                if r.status_code != 200: continue
                meta = r.json()["chart"]["result"][0]["meta"]
                result[cur] = {
                    "current": round(meta["regularMarketPrice"], 1),
                    "prev":    round(meta.get("previousClose", meta["regularMarketPrice"]), 1),
                    "high":    round(meta.get("regularMarketDayHigh", 0), 1),
                    "low":     round(meta.get("regularMarketDayLow",  0), 1),
                }
                break
            except Exception: continue
    return result

@st.cache_data(ttl=60)
def fetch_dxy():
    for host in ["query1", "query2"]:
        try:
            r = requests.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
                params={"interval": "1d", "range": "10d"},
                headers=_H, timeout=8)
            if r.status_code != 200: continue
            res  = r.json()["chart"]["result"][0]
            meta = res["meta"]
            closes = [c for c in res["indicators"]["quote"][0].get("close", []) if c]
            current = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
            if not current: continue
            return {
                "current": round(current, 1),
                "prev":    round(closes[-2], 1) if len(closes) >= 2 else None,
                "high":    round(meta.get("fiftyTwoWeekHigh") or 0, 1),
                "low":     round(meta.get("fiftyTwoWeekLow")  or 0, 1),
            }
        except Exception: continue
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
            params={"from": "USD", "to": "KRW,EUR"}, timeout=10)
        r.raise_for_status()
        raw = r.json()
        usd, eur = [], []
        for ds in sorted(raw.get("rates", {})):
            rates = raw["rates"][ds]
            krw, e = rates.get("KRW"), rates.get("EUR")
            if krw:       usd.append({"date": ds, "rate": round(krw,   1)})
            if krw and e: eur.append({"date": ds, "rate": round(krw/e, 1)})
        return {"USD": usd, "EUR": eur}
    except Exception as e:
        return {"USD": [], "EUR": [], "error": str(e)}

# ── 환율 카드 HTML (index.html 완전 동일) ─────────────────────────────────────
def rate_card(pair, flag, value, prev, high, low, dxy=False):
    if prev and prev > 0:
        chg_pct = (value - prev) / prev * 100
        chg_amt = value - prev
    else:
        chg_pct = chg_amt = 0.0

    dr   = "up" if chg_pct > 0.001 else "down" if chg_pct < -0.001 else ""
    bcls = "up-badge" if dr == "up" else "down-badge" if dr == "down" else "flat-badge"
    arr  = "▲" if dr == "up" else "▼" if dr == "down" else "—"
    ps   = "+" if chg_pct >= 0 else ""
    als  = "+" if chg_amt >= 0 else ""
    unit = "" if dxy else "원"
    top  = "#7c3aed" if dxy else ("#dc2626" if dr == "up" else "#1d4ed8")

    val_s  = f"{value:.1f}"  if dxy else f"{value:,.1f}"
    prev_s = (f"{prev:.1f}"  if dxy else f"{prev:,.1f}") if prev else "—"
    high_s = (f"{high:.1f}"  if dxy else f"{high:,.1f}") if high else "—"
    low_s  = (f"{low:.1f}"   if dxy else f"{low:,.1f}")  if low  else "—"
    amt_s  = f"{als}{chg_amt:.3f}" if dxy else f"{als}{chg_amt:,.1f}원"

    return f"""
<div style="background:#fff;border-radius:14px;padding:24px 20px;text-align:center;
  box-shadow:0 1px 4px rgba(0,0,0,.08);border-top:4px solid {top};
  transition:transform .15s,box-shadow .15s;">
  <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-weight:600;">{pair}</div>
  <div style="font-size:20px;margin:8px 0 4px;">{flag}</div>
  <div style="font-size:32px;font-weight:800;letter-spacing:-1px;margin:4px 0;color:#1e293b;">{val_s}</div>
  <div style="display:flex;align-items:center;justify-content:center;gap:6px;margin-top:4px;">
    <span style="display:inline-flex;align-items:center;gap:4px;font-size:13px;font-weight:700;
      padding:3px 10px;border-radius:20px;
      background:{'#fee2e2' if dr=='up' else '#dbeafe' if dr=='down' else '#f1f5f9'};
      color:{'#dc2626' if dr=='up' else '#1d4ed8' if dr=='down' else '#64748b'};">
      {arr} {ps}{chg_pct:.3f}%
    </span>
    <span style="display:inline-flex;align-items:center;font-size:13px;font-weight:700;
      padding:3px 8px;border-radius:20px;
      background:{'#fee2e2' if dr=='up' else '#dbeafe' if dr=='down' else '#f1f5f9'};
      color:{'#dc2626' if dr=='up' else '#1d4ed8' if dr=='down' else '#64748b'};">
      {amt_s}
    </span>
  </div>
  <div style="font-size:11px;color:#64748b;margin-top:8px;">기준: {prev_s}{unit}</div>
  <div style="display:flex;justify-content:space-around;margin-top:12px;padding-top:12px;
    border-top:1px solid #e2e8f0;font-size:11px;color:#64748b;">
    <span>고가 <strong style="font-weight:600;color:#1e293b;">{high_s}</strong></span>
    <span>저가 <strong style="font-weight:600;color:#1e293b;">{low_s}</strong></span>
  </div>
</div>"""

# ── Section Card 래퍼 ─────────────────────────────────────────────────────────
def section_open(title):
    st.markdown(f"""
<div style="background:#fff;border-radius:14px;padding:24px;
  margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);">
  <div style="font-size:15px;font-weight:700;margin-bottom:18px;color:#1e293b;
    border-left:4px solid #1d4ed8;padding-left:10px;">{title}</div>
""", unsafe_allow_html=True)

def section_close():
    st.markdown("</div>", unsafe_allow_html=True)

# ── DB ────────────────────────────────────────────────────────────────────────
_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fx_monitor.db")

def db_summaries(limit=24):
    if not os.path.exists(_DB): return []
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT hour_label, summary, created_at FROM news_summaries "
            "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return [{"hour_label": r[0], "summary": r[1], "created_at": r[2]} for r in rows]
    except Exception: return []

def db_articles(limit=50):
    if not os.path.exists(_DB): return []
    try:
        con = sqlite3.connect(_DB)
        rows = con.execute(
            "SELECT title, link, published, source_feed, collected_at "
            "FROM yonhap_articles ORDER BY collected_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return rows
    except Exception: return []

# ── Session State ─────────────────────────────────────────────────────────────
if "rate_history" not in st.session_state:
    st.session_state.rate_history = []

# ── 페이지 내용 래퍼 ──────────────────────────────────────────────────────────
st.markdown('<div style="max-width:1100px;margin:0 auto;padding:28px 64px;">', unsafe_allow_html=True)

# ── 탭 ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📊 환율 현황", "📰 연합뉴스 요약", "📋 수집 기사", "⚙️ 설정"])


# ════════════════════════════════════════════════════════════════════════════
# Tab 1 — 환율 현황
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div style="padding:24px 0;">', unsafe_allow_html=True)

    fx  = fetch_rates()
    dxy = fetch_dxy()

    if not fx:
        st.error("환율 수집에 실패했습니다. 잠시 후 다시 시도해주세요.")
        st.stop()

    usd = fx.get("USD", {})
    eur = fx.get("EUR", {})

    # 환율 카드 (3열)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(rate_card("USD / KRW", "🇺🇸",
            usd["current"], usd["prev"], usd["high"], usd["low"]), unsafe_allow_html=True)
    with c2:
        st.markdown(rate_card("EUR / KRW", "🇪🇺",
            eur["current"], eur["prev"], eur["high"], eur["low"]), unsafe_allow_html=True)
    with c3:
        if dxy:
            st.markdown(rate_card("DOLLAR INDEX (DXY)", "📈",
                dxy["current"], dxy["prev"], dxy["high"], dxy["low"], dxy=True), unsafe_allow_html=True)
        else:
            st.warning("DXY 수집 실패")

    # 당일 이력 업데이트
    rec = {"ts": datetime.now().strftime("%H:%M"),
           "USD": usd.get("current"), "EUR": eur.get("current")}
    h = st.session_state.rate_history
    if not h or h[-1].get("USD") != rec["USD"] or h[-1].get("EUR") != rec["EUR"]:
        h.append(rec)
        if len(h) > 100: st.session_state.rate_history = h[-100:]

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 당일 환율 추이 ──────────────────────────────────────────────────────
    section_open("📈 당일 환율 추이")
    if len(st.session_state.rate_history) >= 2:
        mode = st.radio("", ["전체", "USD/KRW", "EUR/KRW"], horizontal=True, key="intraday_mode")
        hist = st.session_state.rate_history
        times = [h["ts"] for h in hist]
        fig = go.Figure()
        if mode in ("전체", "USD/KRW"):
            fig.add_trace(go.Scatter(x=times, y=[h.get("USD") for h in hist],
                name="USD/KRW", line=dict(color="#1d4ed8", width=2),
                hovertemplate="%{y:,.1f}원<extra>USD/KRW</extra>"))
        if mode in ("전체", "EUR/KRW"):
            fig.add_trace(go.Scatter(x=times, y=[h.get("EUR") for h in hist],
                name="EUR/KRW", line=dict(color="#16a34a", width=2),
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
    else:
        st.info("데이터 수집 중입니다. 잠시 후 차트가 표시됩니다.")
    section_close()

    # ── 3개월 환율 추이 ─────────────────────────────────────────────────────
    section_open("📅 3개월 환율 추이")
    hist3 = fetch_history()
    if hist3.get("USD") or hist3.get("EUR"):
        fig2 = go.Figure()
        if hist3.get("USD"):
            fig2.add_trace(go.Scatter(
                x=[d["date"] for d in hist3["USD"]], y=[d["rate"] for d in hist3["USD"]],
                name="USD/KRW", line=dict(color="#1d4ed8", width=2),
                hovertemplate="%{x}<br>%{y:,.1f}원<extra>USD/KRW</extra>"))
        if hist3.get("EUR"):
            fig2.add_trace(go.Scatter(
                x=[d["date"] for d in hist3["EUR"]], y=[d["rate"] for d in hist3["EUR"]],
                name="EUR/KRW", line=dict(color="#16a34a", width=2), yaxis="y2",
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
        section_close()
        section_open("📊 3개월 통계")
        sc1, sc2 = st.columns(2)
        for label, series, col in [("USD/KRW", hist3.get("USD",[]), sc1),
                                     ("EUR/KRW", hist3.get("EUR",[]), sc2)]:
            if not series: continue
            rates = [d["rate"] for d in series]
            max_r, min_r, avg_r = max(rates), min(rates), sum(rates)/len(rates)
            max_d = next(d["date"] for d in series if d["rate"] == max_r)
            min_d = next(d["date"] for d in series if d["rate"] == min_r)
            with col:
                st.markdown(f"""
<div style="margin-bottom:8px;font-size:13px;font-weight:700;color:#1e293b;">{label}</div>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
  <div style="background:#f1f5f9;border-radius:10px;padding:14px 16px;text-align:center;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">🔴 최고가</div>
    <div style="font-size:18px;font-weight:700;color:#1e293b;">{max_r:,.1f}원</div>
    <div style="font-size:11px;color:#64748b;margin-top:2px;">{max_d}</div>
  </div>
  <div style="background:#f1f5f9;border-radius:10px;padding:14px 16px;text-align:center;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">🔵 최저가</div>
    <div style="font-size:18px;font-weight:700;color:#1e293b;">{min_r:,.1f}원</div>
    <div style="font-size:11px;color:#64748b;margin-top:2px;">{min_d}</div>
  </div>
  <div style="background:#f1f5f9;border-radius:10px;padding:14px 16px;text-align:center;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">📊 누계 평균</div>
    <div style="font-size:18px;font-weight:700;color:#1e293b;">{avg_r:,.1f}원</div>
    <div style="font-size:11px;color:#64748b;margin-top:2px;">&nbsp;</div>
  </div>
</div>
""", unsafe_allow_html=True)
    else:
        if "error" in hist3:
            st.warning(f"3개월 데이터 수집 실패: {hist3['error']}")

    section_close()
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# Tab 2 — 연합뉴스 요약
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div style="padding:24px 0;">', unsafe_allow_html=True)
    section_open("📰 연합뉴스 · 인포맥스 환율 기사 요약")

    # 수집 버튼 바
    st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;
  margin-bottom:16px;flex-wrap:wrap;gap:10px;">
  <span style="font-size:13px;color:#64748b;">Groq AI (llama-3.3-70b)로 요약 · 약 30~60초 소요</span>
</div>""", unsafe_allow_html=True)

    if st.button("🔄 지금 수집·요약", key="collect_now"):
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

    section_close()

    # 요약 목록
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
            with st.expander(f"📌 {s['hour_label']}  ·  {s.get('created_at','')}", expanded=(i == 0)):
                st.markdown(s["summary"])
    else:
        st.markdown("""
<div style="text-align:center;padding:48px 24px;color:#64748b;">
  <div style="font-size:40px;margin-bottom:12px;">📭</div>
  <p style="font-size:14px;">아직 요약이 없습니다.<br>위의 <strong>'지금 수집·요약'</strong> 버튼을 눌러주세요.</p>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# Tab 3 — 수집 기사
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div style="padding:24px 0;">', unsafe_allow_html=True)
    section_open("📋 수집 기사 목록")

    articles = db_articles()
    if articles:
        items_html = ""
        for title, link, published, source, collected in articles:
            items_html += f"""
<div style="padding:9px 0;border-bottom:1px solid #e2e8f0;
  font-size:13px;display:flex;align-items:flex-start;gap:8px;">
  <span style="font-size:10px;background:#dbeafe;color:#1d4ed8;
    padding:2px 6px;border-radius:4px;white-space:nowrap;margin-top:2px;flex-shrink:0;">{source}</span>
  <a href="{link}" target="_blank"
    style="color:#1d4ed8;text-decoration:none;flex:1;">{title}</a>
  <span style="font-size:11px;color:#64748b;white-space:nowrap;">{collected[:16] if collected else ''}</span>
</div>"""
        st.markdown(f'<div style="list-style:none;">{items_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown("""
<div style="text-align:center;padding:48px 24px;color:#64748b;">
  <div style="font-size:40px;margin-bottom:12px;">📂</div>
  <p style="font-size:14px;">수집된 기사가 없습니다.<br>'연합뉴스 요약' 탭에서 수집을 시작해주세요.</p>
</div>""", unsafe_allow_html=True)

    section_close()
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# Tab 4 — 설정
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div style="padding:24px 0;">', unsafe_allow_html=True)
    section_open("⚙️ API 키 설정")

    groq_key = get_groq_key()
    if groq_key:
        masked = groq_key[:8] + "****" + groq_key[-4:]
        st.success(f"✅ Groq API 키 설정됨: `{masked}`")
        if st.button("🧪 연결 테스트"):
            with st.spinner("테스트 중..."):
                try:
                    from groq import Groq
                    res = Groq(api_key=groq_key).chat.completions.create(
                        model="llama-3.3-70b-versatile", max_tokens=20,
                        messages=[{"role":"user","content":"환율을 한 단어로 표현하면?"}])
                    st.success(f"✅ 연결 성공! 응답: {res.choices[0].message.content.strip()}")
                except Exception as e:
                    st.error(f"❌ 연결 실패: {e}")
    else:
        st.error("❌ Groq API 키가 설정되지 않았습니다.")

    section_close()

    section_open("🔑 Streamlit Secrets에 API 키 설정하는 방법")
    st.markdown("""
<div style="font-size:13px;color:#374151;line-height:1.8;">
<strong>Streamlit Community Cloud 배포 시:</strong><br>
1. <a href="https://share.streamlit.io" target="_blank" style="color:#1d4ed8;">share.streamlit.io</a> 접속 → 앱 선택<br>
2. 우측 상단 <strong>⋮ → Settings → Secrets</strong> 클릭<br>
3. 아래 내용 입력 후 저장:
</div>""", unsafe_allow_html=True)
    st.code('GROQ_API_KEY = "gsk_xxxxxxxxxx"', language="toml")
    section_close()

    section_open("📊 시스템 정보")
    st.markdown("""
<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;">
  <div style="background:#f1f5f9;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">대상 통화</div>
    <div style="font-size:14px;font-weight:600;">USD/KRW · EUR/KRW</div>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">환율 소스</div>
    <div style="font-size:14px;font-weight:600;">Yahoo Finance (실시간)</div>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">뉴스 소스</div>
    <div style="font-size:14px;font-weight:600;">연합뉴스 · 연합인포맥스</div>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">AI 모델</div>
    <div style="font-size:14px;font-weight:600;">Groq llama-3.3-70b</div>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">이력 소스</div>
    <div style="font-size:14px;font-weight:600;">Frankfurter API (3개월)</div>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">갱신 주기</div>
    <div style="font-size:14px;font-weight:600;">1분 자동 갱신</div>
  </div>
</div>""", unsafe_allow_html=True)
    section_close()

    st.markdown("</div>", unsafe_allow_html=True)

# 페이지 래퍼 닫기
st.markdown("""
</div>
<footer style="text-align:center;font-size:12px;color:#64748b;
  padding:24px;border-top:1px solid #e2e8f0;margin-top:8px;">
  FX Monitor · Yahoo Finance · Frankfurter API · Groq AI
</footer>
""", unsafe_allow_html=True)
