import asyncio
from datetime import datetime, timedelta, timezone
import crud
from database import AsyncSessionLocal
from constants import COUNTRY_MAP
# 🎯 그래프 내부에서 국가 분석을 담당하는 실제 '노드 함수'를 직접 가져옵니다.
from analysis_graph import node_analyze_country 
yesterday = datetime.now(timezone.utc) - timedelta(days=1)
target_date_str = yesterday.strftime('%Y-%m-%d')

async def test_country_analysis_only(event_uri: str):
    async with AsyncSessionLocal() as session:
        # 1. DB 데이터 로드
        articles = await crud.get_analyzed_articles_by_event(session, event_uri)
        event = await crud.get_event_by_uri(session, event_uri)

        # 2. 노드가 요구하는 포맷으로 상태값(State) 구성
        mock_results = []
        for a in articles:
            # 💡 기존의 국가 코드 'unknown' 방어 코드가 여기 들어가 있네요!
            mock_results.append({
                "country_code": COUNTRY_MAP.get(a.country_uri, "unknown"),
                "raw_analysis": {
                    "score_sentiment": {"score": a.score_sentiment},
                    "score_objectivity": {"score": a.score_objectivity},
                    "score_urgency": {"score": a.score_urgency},
                    "score_credibility": {"score": a.score_credibility},
                    "score_sensationalism": {"score": a.score_sensationalism},
                    "analysis_summary_en": a.analysis_summary_en
                }
            })

        state = {
            "event_uri": event_uri,
            "event_info": {"title_main": event.title_main, "summary_main": event.summary_main},
            "analysis_results": mock_results,
            "articles": [],
            "current_article": None
        }

        # 📂 backend/test_country_analysis.py 내부 저장 로직 수정

        print(f"🚀 {event_uri} 국가 분석 노드 단독 실행 중...")
        final_state = await node_analyze_country(state) 
        
        # 1. 전체 파일 스키마에 맞게 country_analysis_results 리스트 추출
        raw_country_results = final_state.get("country_analysis_results", []) 
        
        if raw_country_results:
            print(f"📦 적재할 국가 분석 데이터 존재: {len(raw_country_results)}건")
            
            # 2. 전체 파일 기준(List[dict])에 맞추기 위해 리스트 내부 요소 정제
            import json
            cleaned_results = []
            for item in raw_country_results:
                if isinstance(item, str):
                    try:
                        cleaned_results.append(json.loads(item))
                    except json.JSONDecodeError:
                        print(f"❌ JSON 디코딩 실패 스트링 스킵: {item}")
                elif isinstance(item, dict):
                    cleaned_results.append(item)
            
            # 3. 🎯 반복문(for) 없이 리스트를 '통째로' 전달 (전체 파일의 node_save_results와 동일한 방식)
            try:
                await crud.upsert_country_analysis(session, event_uri, cleaned_results, target_date_str)
                await session.commit()
                print("🏆 country_event_analysis 테이블 최종 커밋 완료!")
            except Exception as e:
                await session.rollback()
                print(f"❌ DB 반영 실패 (롤백 처리됨): {e}")
        else:
            print("⚠️ 국가 분석 결과 데이터가 비어 있습니다.")

if __name__ == "__main__":
    uri = "eng-11665783"
    asyncio.run(test_country_analysis_only(uri))