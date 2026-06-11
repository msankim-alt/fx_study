"""
연합뉴스 환율 기사 시간별 수집 스케줄러
매시 정각(HH:00) + 매시 30분(HH:30) 실행
단독 실행 또는 main.py와 별도로 운용 가능
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from yonhap_news import init_news_db, run_news_pipeline
from datetime import datetime


def job():
    print(f"\n{'='*50}")
    print(f"  [스케줄 실행] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    try:
        run_news_pipeline()
    except Exception as e:
        print(f"[ERROR] 파이프라인 오류: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("  연합뉴스 환율 기사 수집 스케줄러")
    print("  매시 정각(HH:00) + 매시 30분(HH:30) 자동 실행")
    print("=" * 50)

    init_news_db()

    # 즉시 1회 실행
    print("\n[INFO] 초기 수집 실행...")
    job()

    # 매시 정각·30분 스케줄 등록
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(job, "cron", minute="0,30")   # HH:00 · HH:30

    print("\n[INFO] 스케줄러 실행 중... 매시 정각·30분에 자동 수집합니다. (Ctrl+C 로 종료)")
    scheduler.start()
