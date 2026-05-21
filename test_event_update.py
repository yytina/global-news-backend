import asyncio
from sqlalchemy import select, func, update
from database import AsyncSessionLocal
from models import Event, Article

async def test_update_event_sentiment(event_uri: str):
    async with AsyncSessionLocal() as session:
        print(f"🔍 사건 {event_uri} 점수 업데이트 테스트 시작...")
        
        # 1. DB에서 해당 사건의 기사 점수들 직접 조회
        stmt = select(Article.score_sentiment).where(
            Article.event_uri == event_uri,
            Article.analysis_status == 'COMPLETED'
        )
        result = await session.execute(stmt)
        scores = [row[0] for row in result.all() if row[0] is not None]
        
        if not scores:
            print("⚠️ 분석 완료된 기사가 없습니다.")
            return

        # 2. 평균 계산
        avg_val = sum(scores) / len(scores)
        print(f"📊 계산된 평균 점수: {avg_val} (기사 수: {len(scores)})")

        # 3. Event 테이블 업데이트
        await session.execute(
            update(Event)
            .where(Event.uri == event_uri)
            .values({
                "avg_sentiment": round(avg_val, 4),
                "updated_at": func.now()
            })
        )
        await session.commit()
        print(f"✅ DB 업데이트 성공! 이제 Supabase를 확인하세요.")

if __name__ == "__main__":
    # 테스트하고 싶은 event_uri를 여기에 넣으세요
    target_uri = "eng-11653362" 
    asyncio.run(test_update_event_sentiment(target_uri))