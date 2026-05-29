# ingestion_service.py
from datetime import datetime
import news_api
import crud
import schemas
from database import AsyncSessionLocal

async def run_daily_ingestion():
    top3_events = await news_api.get_refined_top3_events() 
    
    # 🎯 루프 외부 통짜 commit을 제거하고, 각 이벤트마다 격리된 트랜잭션을 적용합니다.
    for event in top3_events:
        # 이벤트 하나당 하나의 독립된 세션 스코프 분리
        async with AsyncSessionLocal() as session:
            try:
                # 명시적으로 트랜잭션 블록 개시 (오토 커밋/롤백 보장)
                async with session.begin():
                    
                    # 1. 데이터 매핑
                    event_schema = schemas.EventCreate(
                        uri=event['uri'],
                        title_main=event.get('title', {}).get('eng') or next(iter(event.get('title', {}).values()), "No Title"),
                        summary_main=event.get('summary', {}).get('eng') or next(iter(event.get('summary', {}).values()), ""),
                        all_titles=event.get('title', {}),
                        all_summaries=event.get('summary', {}),
                        size=event.get('totalArticleCount', 0),
                        article_counts=event.get('articleCounts', {}),
                        epicenter_country_uri=news_api.get_event_epicenter_wiki(event),
                        target_country_uris=news_api.get_target_country_uris(event['articleCounts']),
                        date=news_api.get_yesterday_utc()
                    )

                    # 2. [CRUD] 이벤트 저장
                    await crud.upsert_event(session, event_schema)
                    
                    # 3. [API] 국가별 기사 수집 및 검증
                    all_article_schemas = []
                    for target_uri in event_schema.target_country_uris:
                        # ⚡ 네트워크 타임아웃 위험 구간 예외 처리
                        try:
                            raw_articles = await news_api.get_articles_by_event_and_location(event_schema.uri, target_uri)
                            for art in raw_articles:
                                all_article_schemas.append(schemas.ArticleSource(
                                    uri=art['uri'],
                                    date=news_api.get_yesterday_utc(),
                                    event_uri=event_schema.uri,
                                    country_uri=target_uri,
                                    lang_code=art.get('lang', 'unk'),
                                    title=art.get('title', 'No Title'),
                                    body=art.get('body', ''),
                                    url=art.get('url', '')
                                ))
                        except Exception as api_err:
                            print(f"⚠️ {event_schema.uri} [{target_uri}] 기사 수집 중 네트워크 에러 패스: {api_err}")
                            continue
                    
                    # 4. [CRUD] 기사 벌크 저장
                    if all_article_schemas:
                        added_count = await crud.create_articles(session, all_article_schemas)
                        print(f"📦 {event_schema.uri}: {added_count} articles added.")
                
                # Context 블록을 나가면서 이 이벤트에 대한 데이터는 물리 DB에 즉시 확실하게 COMMIT 됨
                print(f"✅ 이벤트 {event_schema.uri} 데이터 영속화 완료.")

            except Exception as e:
                # 이 이벤트가 실패해도 session.begin()에 의해 이 세션만 자동으로 ROLLBACK 됨
                # 루프가 깨지지 않으므로 다음 이벤트 수집은 정상 진행 가능
                print(f"❌ 이벤트 {event.get('uri')} 처리 중 치명적 에러 발생 (해당 이벤트 롤백): {e}")
                continue
    
    print("🚀 오늘의 뉴스 수집 파이프라인 완료!")
    return list(map(lambda x: x['uri'], top3_events))