import os
import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from collector import fetch_exchange_rates, fetch_news, fetch_rss
from analyzer import detect_change, analyze_with_claude
from reporter import generate_report
from database import init_db, save_rates, save_report, get_history

# 수집 시간 범위 (오전 8시 ~ 오후 5시)
COLLECT_START = 8
COLLECT_END   = 17

# 직전 환율 (메모리 캐시)
prev_rates: dict = {}


def is_collect_time() -> bool:
    """현재 시각이 수집 허용 시간(08:00~17:00)인지 확인"""
    now = datetime.datetime.now()
    return COLLECT_START <= now.hour < COLLECT_END


def run_pipeline():
    global prev_rates

    now_str = datetime.datetime.now().strftime("%H:%M:%S")

    if not is_collect_time():
        print(f"\n[{now_str}] 수집 시간 외 ({COLLECT_START}:00~{COLLECT_END}:00), 스킵")
        return

    print(f"\n[{now_str}] 파이프라인 실행")

    # 1. 환율 수집 (USD·EUR — 엔화 제외)
    curr_rates = fetch_exchange_rates()
    if not curr_rates or all(v is None for v in curr_rates.values()):
        print("[WARN] 환율 수집 실패, 스킵")
        return

    save_rates(curr_rates)

    # 2. 변동 감지
    changes, triggered = detect_change(prev_rates, curr_rates)
    print(f"[INFO] 변동: USD {changes.get('USD', 0):+.3f}%  "
          f"EUR {changes.get('EUR', 0):+.3f}%")

    # 3. 임계값 초과 or 최초 실행 → 보고서 생성
    if triggered or not prev_rates:
        print("[INFO] 보고서 생성 시작...")

        news = fetch_news("환율 달러 원화 외환") + fetch_rss()
        analysis = analyze_with_claude(curr_rates, changes, news)
        history = get_history(limit=60)

        filepath = generate_report(curr_rates, changes, analysis, news, history)
        save_report(filepath, changes, analysis)

        print(f"[OK] 보고서: {filepath}")
    else:
        print("[INFO] 변동 임계값 미달, 대기")

    prev_rates = curr_rates


if __name__ == "__main__":
    print("=" * 50)
    print("  환율 모니터링 시스템 시작")
    print(f"  수집 시간: {COLLECT_START:02d}:00 ~ {COLLECT_END:02d}:00")
    print("  수집 간격: 5분")
    print("=" * 50)

    init_db()

    # 수집 시간이면 즉시 1회 실행
    if is_collect_time():
        run_pipeline()

    # 스케줄러 등록 (5분 간격)
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(run_pipeline, "interval", minutes=5)

    print("\n[INFO] 스케줄러 실행 중... (Ctrl+C 로 종료)")
    scheduler.start()
