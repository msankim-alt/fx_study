import plotly.graph_objects as go
from jinja2 import Template
from datetime import datetime
import os

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>환율 변동 보고서 — {{ generated_at }}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
           background: #f8fafc; color: #1e293b; padding: 32px; }
    .container { max-width: 960px; margin: 0 auto; }
    .header { border-bottom: 3px solid #1d4ed8; padding-bottom: 16px; margin-bottom: 28px; }
    .header h1 { font-size: 24px; font-weight: 700; color: #1e293b; }
    .header p  { font-size: 13px; color: #64748b; margin-top: 4px; }
    .rate-grid { display: grid; grid-template-columns: repeat(3, 1fr);
                 gap: 16px; margin-bottom: 28px; }
    .rate-card { background: #ffffff; border-radius: 12px; padding: 24px;
                 text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .rate-card .pair  { font-size: 12px; color: #64748b; text-transform: uppercase; }
    .rate-card .value { font-size: 30px; font-weight: 700; margin: 8px 0; }
    .rate-card .change { font-size: 15px; font-weight: 600; }
    .up   { color: #dc2626; }
    .down { color: #2563eb; }
    .flat { color: #64748b; }
    section { background: #ffffff; border-radius: 12px; padding: 24px;
              margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    section h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px;
                 color: #1e293b; border-left: 4px solid #1d4ed8;
                 padding-left: 10px; }
    .analysis { white-space: pre-wrap; line-height: 1.8; font-size: 14px; color: #374151; }
    .news-list { list-style: none; }
    .news-list li { padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
    .news-list li:last-child { border-bottom: none; }
    .news-list a { color: #1d4ed8; text-decoration: none; }
    .news-list a:hover { text-decoration: underline; }
    .news-source { font-size: 11px; color: #94a3b8; margin-left: 6px; }
    .footer { text-align: center; font-size: 12px; color: #94a3b8; margin-top: 32px; }
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 환율 변동 보고서</h1>
    <p>생성 일시: {{ generated_at }} | 변동 임계값: ±0.5%</p>
  </div>

  <div class="rate-grid">
    {% for cur, data in rates.items() %}
    <div class="rate-card">
      <div class="pair">{{ cur }}/KRW</div>
      <div class="value">{{ "{:,.2f}".format(data.value) }}원</div>
      <div class="change {{ 'up' if data.change > 0 else ('down' if data.change < 0 else 'flat') }}">
        {{ '+' if data.change > 0 else '' }}{{ "{:.3f}".format(data.change) }}%
      </div>
    </div>
    {% endfor %}
  </div>

  <section>
    <h2>환율 추이 차트</h2>
    {{ chart_html }}
  </section>

  <section>
    <h2>AI 변동 요인 분석</h2>
    <div class="analysis">{{ analysis }}</div>
  </section>

  <section>
    <h2>관련 뉴스 및 공식 발표</h2>
    <ul class="news-list">
      {% for item in news_items[:10] %}
      <li>
        <a href="{{ item.link }}" target="_blank">{{ item.title }}</a>
        {% if item.get('source') %}
        <span class="news-source">[{{ item.source }}]</span>
        {% endif %}
      </li>
      {% endfor %}
    </ul>
  </section>

  <div class="footer">자동 생성된 보고서입니다. 투자 판단의 최종 책임은 이용자에게 있습니다.</div>
</div>
</body>
</html>"""


def build_chart(history: list) -> str:
    """Plotly로 환율 추이 차트 생성 (HTML 조각 반환)"""
    if not history:
        return "<p style='color:#94a3b8;font-size:13px'>수집된 이력 데이터가 없습니다.</p>"

    fig = go.Figure()
    colors = {"USD": "#1d4ed8", "JPY": "#dc2626", "EUR": "#16a34a"}

    for cur in ["USD", "JPY", "EUR"]:
        fig.add_trace(go.Scatter(
            x=[h["timestamp"] for h in history],
            y=[h.get(cur) for h in history],
            name=f"{cur}/KRW",
            mode="lines+markers",
            line=dict(color=colors[cur], width=2),
            marker=dict(size=5)
        ))

    fig.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=8, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
        yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
        font=dict(family="'Noto Sans KR', sans-serif", size=12)
    )

    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def generate_report(rates: dict, changes: dict, analysis: str,
                    news_items: list, history: list) -> str:
    """HTML 보고서 파일 생성 후 경로 반환"""
    chart_html = build_chart(history)

    template = Template(HTML_TEMPLATE)
    html = template.render(
        generated_at=datetime.now().strftime("%Y년 %m월 %d일 %H:%M:%S"),
        rates={
            cur: type("obj", (), {
                "value": rates.get(cur, 0),
                "change": changes.get(cur, 0)
            })()
            for cur in ["USD", "JPY", "EUR"]
        },
        chart_html=chart_html,
        analysis=analysis,
        news_items=news_items
    )

    filename = os.path.join(
        REPORT_DIR,
        f"fx_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[INFO] 보고서 생성: {filename}")
    return filename
