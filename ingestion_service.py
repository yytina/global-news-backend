# ingestion_service.py
from datetime import datetime
import news_api
import crud
import schemas
from database import AsyncSessionLocal

async def run_daily_ingestion():
    top3_events = await news_api.get_refined_top3_events() 
    
    async with AsyncSessionLocal() as session:
        for event in top3_events:
            # 1. 데이터 매핑 (Raw Dict -> Pydantic Schema)
            # 가공 로직을 schema 생성 시점에 처리하여 코드가 깔끔해집니다.
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

            # 2. [CRUD] 이벤트 저장 (딕셔너리 대신 스키마 객체 전달)
            await crud.upsert_event(session, event_schema)
            
            # 3. [API] 국가별 기사 수집 및 검증
            all_article_schemas = []
            for target_uri in event_schema.target_country_uris:
                raw_articles = await news_api.get_articles_by_event_and_location(event_schema.uri, target_uri)
                
                for art in raw_articles:
                    # 각 기사를 ArticleSource 스키마로 변환 (데이터 검증)
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
            
            # 4. [CRUD] 기사 벌크 저장
            if all_article_schemas:
                added_count = await crud.create_articles(session, all_article_schemas)
                print(f"📦 {event_schema.uri}: {added_count} articles added.")

        await session.commit()
    
    print("🚀 오늘의 뉴스 수집 파이프라인 완료!")
    return list(map(lambda x:x['uri'], top3_events))