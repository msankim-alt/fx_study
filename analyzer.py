from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

THRESHOLD = 0.5  # 변동 감지 임계값 (%)


def detect_change(prev_rates: dict, curr_rates: dict) -> tuple:
    """
    직전 환율 대비 변동률 계산
    Returns: (변동률 dict, 임계값 초과 여부)
    """
    changes = {}
    triggered = False

    for cur in ["USD", "EUR"]:
        if prev_rates.get(cur) and curr_rates.get(cur):
            pct = (curr_rates[cur] - prev_rates[cur]) / prev_rates[cur] * 100
            changes[cur] = round(pct, 3)
            if abs(pct) >= THRESHOLD:
                triggered = True

    return changes, triggered


def analyze_with_claude(rates: dict, changes: dict, news_items: list) -> str:
    """
    Gemini API를 활용한 환율 변동 요인 분석
    뉴스 + 환율 데이터를 종합하여 AI 분석 리포트 생성
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return "[AI 분석 오류] GROQ_API_KEY가 설정되지 않았습니다."

    client = Groq(api_key=api_key)

    news_text = "\n".join([
        f"- {n['title']}: {n.get('desc', n.get('summary', ''))}"
        for n in news_items[:12]
    ])

    prompt = f"""당신은 외환시장 전문 애널리스트입니다.
아래 환율 데이터와 최신 뉴스를 바탕으로 환율 변동 요인을 분석해주세요.

## 현재 환율 및 변동
- USD/KRW: {rates.get('USD', 'N/A')}원  ({changes.get('USD', 0):+.3f}%)
- EUR/KRW: {rates.get('EUR', 'N/A')}원  ({changes.get('EUR', 0):+.3f}%)

## 최신 뉴스 (수집 시각 기준)
{news_text}

## 분석 요청 항목
1. **주요 변동 요인** (상위 3가지, 영향도 순)
2. **국내 요인 분석** (경기, 무역수지, 금리 등)
3. **해외 요인 분석** (미 연준, 글로벌 리스크, 지정학 등)
4. **단기 전망** (향후 1~3 거래일)
5. **투자자 참고사항**

전문적이고 간결하게 작성해주세요."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[AI 분석 오류] {e}"
