import asyncio
import json
from analysis_graph import node_analyze_article, node_save_results
from database import AsyncSessionLocal
import crud
from sqlalchemy import select
from models import Article, Event
from dotenv import load_dotenv

load_dotenv()

async def analyze_all_articles_of_event(event_uri: str):
    async with AsyncSessionLocal() as session:
        # 1. 해당 사건의 모든 기사 중 아직 분석되지 않은(PENDING) 기사들 가져오기
        stmt = select(Article).where(
            Article.event_uri == event_uri,
            Article.analysis_status == "PENDING"
        )
        result = await session.execute(stmt)
        pending_articles = result.scalars().all()
        
        event = await crud.get_event_by_uri(session, event_uri)
        
        if not event:
            print(f"❌ 사건({event_uri})을 찾을 수 없습니다.")
            return
        
        if not pending_articles:
            print(f"✅ 사건({event_uri})에 더 이상 분석할 기사가 없습니다.")
            return

        print(f"🚀 사건 '{event.title_main}' 분석 시작 (대상 기사: {len(pending_articles)}개)")

        all_analysis_results = []

        # 2. 루프를 돌며 개별 기사 분석 실행
        for idx, article in enumerate(pending_articles):
            print(f"[{idx+1}/{len(pending_articles)}] '{article.title}' 분석 중...")
            
            state = {
                "current_article": {"uri": article.uri, "title": article.title, "body": article.body},
                "event_info": {"title_main": event.title_main, "summary_main": event.summary_main},
                "analysis_results": []
            }
            
            try:
                # 개별 기사 분석 노드 실행
                res = await node_analyze_article(state)
                if res.get("analysis_results"):
                    all_analysis_results.extend(res["analysis_results"])
            except Exception as e:
                print(f"   ⚠️ '{article.title}' 분석 실패: {e}")

        # 3. 통합 결과 저장 및 사건 평균 점수 업데이트
        # node_save_results가 'country_analysis_results'도 기대하므로 빈 리스트를 넣어줍니다.
        final_state = {
            "event_uri": event_uri,
            "analysis_results": all_analysis_results,
            "country_analysis_results": [] # 필요 시 여기에 국가 분석 결과 추가 가능
        }

        print(f"\n💾 총 {len(all_analysis_results)}개의 분석 결과 저장 및 사건 지수 업데이트 시작...")
        save_result = await node_save_results(final_state)
        print(f"🏁 최종 상태: {save_result.get('final_status', 'COMPLETED')}")

if __name__ == "__main__":
    # 💡 테스트하려는 event_uri를 여기에 입력하세요.
    # target_event_uri = "spa-4197658" eng-11656606
    target_event_uri = "eng-11656606" 
    asyncio.run(analyze_all_articles_of_event(target_event_uri))