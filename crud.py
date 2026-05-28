from datetime import datetime, timedelta, timezone
from typing import List
from sqlalchemy import desc, func, select, desc, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from models import Event, Article, CountryEventAnalysis
import schemas
from constants import COUNTRY_MAP

def get_date_from_str(date_str: str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception as e:
        # 날짜 형식이 잘못되었을 경우를 대비한 안전장치
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

async def upsert_event(session: AsyncSession, event_data: schemas.EventCreate):
    # 1. Pydantic 스키마를 순수 파이썬 dict로 안전하게 덤프
    raw_data = event_data.model_dump()
    
    # 2. 빌더 패턴 구성
    stmt = insert(Event).values(**raw_data)
    
    # 3. 충돌 시 업데이트 제어 구조 정상화
    stmt = stmt.on_conflict_do_update(
        index_elements=['uri'],
        set_={
            # 충돌이 났을 때, 새로 들어온 데이터(EXCLUDED)의 값으로 덮어쓰도록 명시합니다.
            "size": stmt.excluded.size,
            "article_counts": stmt.excluded.article_counts,
            "updated_at": func.now(),
            "all_titles": stmt.excluded.all_titles,
            "all_summaries": stmt.excluded.all_summaries,
            "title_main": stmt.excluded.title_main,
            "summary_main": stmt.excluded.summary_main
        }
    )
    
    await session.execute(stmt)
    # 호출부(ingestion_service.py)나 이곳 중 한 곳에서 커밋을 보장해야 트랜잭션이 끝납니다. 

async def get_top_daily_events(db: AsyncSession, limit: int = 3, target_date: str = None):
    # 1. 문자열을 파이썬 date 객체로 변환
    # target_date가 '2026-05-13' 형태의 문자열이라면:
    date_obj = get_date_from_str(target_date)

    query = (
        select(Event)
        # 💡 이제 cast 없이 직접 비교해도 SQLAlchemy가 완벽하게 처리합니다.
        .where(Event.date == date_obj)
        .where(Event.analysis_status == "PENDING") 
        .order_by(desc(Event.size))
        .limit(limit)
    )

    result = await db.execute(query)
    events = result.scalars().all()
    return events

async def get_yesterday_events(session: AsyncSession):
    """
    DB의 'event_date' 컬럼값이 UTC 기준 어제 날짜인 이벤트들을 반환합니다.
    """
    # 1. 기준이 되는 어제 날짜 계산
    yesterday_utc = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    
    # 2. 쿼리 작성 (event_date가 어제와 일치하는 것들)
    query = select(Event).where(Event.date == yesterday_utc)
    
    # 3. 실행 및 결과 반환
    result = await session.execute(query)
    events = result.scalars().all()
    
    print(f"🔍 {yesterday_utc} 날짜의 이벤트를 {len(events)}개 찾았습니다.")
    return events

async def create_articles(session: AsyncSession, articles_data: List[schemas.ArticleSource]):
    if not articles_data:
        return 0

    # 1. 스키마 리스트를 딕셔너리 리스트로 변환
    values = [art.model_dump() for art in articles_data]

    # 2. PostgreSQL용 insert 구문 생성
    stmt = insert(Article).values(values)

    # 3. 충돌 시 아무것도 하지 않음 (uri가 중복되면 해당 row는 skip)
    stmt = stmt.on_conflict_do_nothing(index_elements=['uri'])
    # stmt = stmt.on_conflict_do_update(
    #         set_={
    #             "analysis_summary_en": stmt.excluded.analysis_summary_en, # 👈 누락 주의
    #             "analyzed_at": func.now() # 분석 시점 갱신
    #         }
    #     )

    # 4. 실행
    result = await session.execute(stmt)
    
    # 추가된 행의 수 반환 (on_conflict_do_nothing 사용 시 행 수 계산이 정확하지 않을 수 있어 len으로 대체 가능)
    return len(articles_data)

# crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Article, Event

async def get_one_pending_article(db: AsyncSession):
    """
    분석 대기 중(PENDING)인 기사 하나를 가져옵니다.
    """
    query = select(Article).where(Article.analysis_status == "PENDING").limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_event_by_uri(db: AsyncSession, event_uri: str):
    """
    특정 URI에 해당하는 이벤트 정보를 가져옵니다.
    """
    query = select(Event).where(Event.uri == event_uri)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_article_by_uri(db: AsyncSession, article_uri: str):
    """
    특정 URI에 해당하는 이벤트 정보를 가져옵니다.
    """
    query = select(Article).where(Article.uri == article_uri)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_articles_by_event(db: AsyncSession, event_uri: str):
    """
    특정 이벤트(event_uri)에 속한 모든 기사를 가져옵니다.
    보통 분석 상태가 'PENDING'인 기사들 위주로 가져오도록 필터를 걸 수도 있습니다.
    """
    query = select(Article).where(Article.event_uri == event_uri)
    result = await db.execute(query)
    return result.scalars().all()

# async def get_analyzed_articles_by_event(db: AsyncSession, event_uri: str):
#     """
#     이벤트의 분석 상태를 체크하고, 완료된 경우에만 기사 리스트를 반환합니다.
#     """
#     # 1. 이벤트의 상태를 먼저 조회합니다.
#     event_query = select(Event).where(Event.uri == event_uri)
#     event_result = await db.execute(event_query)
#     event = event_result.scalar_one_or_none()

#     if not event:
#         return {"status": "ERROR", "message": "Event not found"}

#     # 2. 분석 상태 체크
#     # (analysis_status가 'COMPLETED'인 경우에만 통과)
#     if event.analysis_status != "COMPLETED":
#         return {
#             "status": "PENDING", 
#             "message": "AI analysis is in progress. Please try again later."
#         }

#     # 3. 분석이 완료되었다면 기사들을 가져옵니다.
#     # 이때, 혹시 모를 누락을 방지하기 위해 기사 자체의 status도 'COMPLETED'인 것만 필터링합니다.
#     article_query = (
#         select(Article)
#         .where(Article.event_uri == event_uri)
#         .where(Article.analysis_status == "COMPLETED")
#         # 관련성 높은 순서대로 가져오면 나중에 5개 끊기가 편합니다.
#         .order_by(Article.relevance.desc()) 
#     )
#     article_result = await db.execute(article_query)
#     articles = article_result.scalars().all()

#     if not articles:
#         return {"status": "EMPTY", "message": "No analyzed articles found for this event."}

#     return {
#         "status": "SUCCESS",
#         "data": articles
#     }

# crud.py (예상되는 문제 지점)

async def get_analyzed_articles_by_event(db: AsyncSession, event_uri: str):
    # ❌ 기존 (문자열 리스트가 반환되는 이유):
    # result = await db.execute(select(Article.analysis_status).where(...))
    
    # ✅ 수정 (객체 전체를 가져와야 .country_uri 등에 접근 가능):
    result = await db.execute(
        select(Article).where(
            Article.event_uri == event_uri,
            Article.analysis_status == "COMPLETED"
        )
    )
    return result.scalars().all() # scalar()가 아닌 scalars().all()로 객체 리스트 반환

async def get_articles_by_event_and_country(db, event_uri: str, country_code: str, target_date: str = None):
    date_obj = get_date_from_str(target_date)
    target_code = country_code.lower()

    # 1. Extract base URIs without protocol headers from COUNTRY_MAP
    raw_uris = [
        wiki_url for wiki_url, code in COUNTRY_MAP.items() 
        if code == target_code
    ]
    
    # 2. Build a comprehensive list containing BOTH http and https variants
    matched_uris = []
    for uri in raw_uris:
        # Strip existing protocol if present
        clean_uri = uri.replace("https://", "").replace("http://", "")
        # Append both variants to catch any database discrepancies safely
        matched_uris.append(f"https://{clean_uri}")
        matched_uris.append(f"http://{clean_uri}")

    if not matched_uris:
        print(f"⚠️ COUNTRY_MAP에서 해당 국가 코드를 찾을 수 없습니다: {country_code}")
        return []

    # 3. IN operator now seamlessly catches both http and https rows
    stmt = (
        select(Article)
        .where(
            Article.event_uri == event_uri,
            Article.country_uri.in_(matched_uris),
            Article.date == date_obj
        )
        .order_by(Article.date.desc())
    )
    
    result = await db.execute(stmt)
    return result.scalars().all()


from sqlalchemy.dialects.postgresql import insert

async def upsert_country_analysis(
        session: AsyncSession, 
        event_uri: str, 
        results: list, 
        target_date: str
        ):
    date_obj = get_date_from_str(target_date)
    for res in results:
        # Pydantic/Dict 데이터를 DB 필드에 맞게 매핑
        # 1. strategic_analysis 보따리 먼저 꺼내기
        strat = res.get("strategic_analysis", {})
        metrics = res.get("metrics", {})

        insert_stmt = insert(CountryEventAnalysis).values(
            date=date_obj,
            event_uri=event_uri,
            country_code=res.get("country_code"),
            
            # metrics 보따리에서 꺼내기
            score_sentiment=metrics.get("score_sentiment", {}).get("score", 0.0),
            score_objectivity=metrics.get("score_objectivity", {}).get("score", 0.0),
            score_urgency=metrics.get("score_urgency", {}).get("score", 0.0),
            score_credibility=metrics.get("score_credibility", {}).get("score", 0.0),
            score_sensationalism=metrics.get("score_sensationalism", {}).get("score", 0.0),
            
            # 💡 strategic_analysis 보따리에서 꺼내기 (여기가 포인트!)
            consensus_rate=strat.get("consensus_rate", 0.0),
            national_interest=strat.get("national_interest", ""), # 이제 텍스트가 들어옵니다!
            strategic_frame=strat.get("strategic_frame", ""),     # 이제 텍스트가 들어옵니다!
            
            analysis_summary_kr=res.get("analysis_summary_kr", ""),
            analysis_summary_en=res.get("analysis_summary_en", "")
        )
        # PK 충돌(event_uri + country_code) 시 업데이트 수행
        # PK 충돌(event_uri + country_code) 시 업데이트 수행
        do_update_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['event_uri', 'country_code', 'date'],
            set_={
                "score_sentiment": insert_stmt.excluded.score_sentiment,
                "score_objectivity": insert_stmt.excluded.score_objectivity,
                "score_urgency": insert_stmt.excluded.score_urgency,
                "score_credibility": insert_stmt.excluded.score_credibility,
                "score_sensationalism": insert_stmt.excluded.score_sensationalism,
                "consensus_rate": insert_stmt.excluded.consensus_rate,
                "national_interest": insert_stmt.excluded.national_interest, # 👈 추가 확인!
                "strategic_frame": insert_stmt.excluded.strategic_frame,     # 👈 추가 확인!
                "analysis_summary_kr": insert_stmt.excluded.analysis_summary_kr,
                "analysis_summary_en": insert_stmt.excluded.analysis_summary_en, # 👈 누락 주의
                "analyzed_at": func.now() # 분석 시점 갱신
            }
        )
        await session.execute(do_update_stmt)

# crud.py

from sqlalchemy import select
from models import Event, Article

async def get_event_analysis_package(db: AsyncSession, event_uri: str):
    """
    main.py의 Map Data 로직이 기대하는 {status, event, data} 구조를 반환합니다.
    """
    try:
        # 1. 이벤트 정보 가져오기
        event_stmt = select(Event).where(Event.uri == event_uri)
        event_result = await db.execute(event_stmt)
        event = event_result.scalar_one_or_none()

        if not event:
            return {"status": "ERROR", "message": "Event not found"}

        # 2. 분석 완료된 기사들 가져오기
        article_stmt = select(Article).where(
            Article.event_uri == event_uri,
            Article.analysis_status == "COMPLETED"
        )
        article_result = await db.execute(article_stmt)
        articles = article_result.scalars().all()

        # 💡 main.py가 기대하는 바로 그 구조
        return {
            "status": "SUCCESS",
            "event": event,
            "data": articles
        }
    except Exception as e:
        print(f"❌ Comprehensive Data Fetch Error: {e}")
        return {"status": "ERROR", "message": str(e)}
    

async def get_event_country_analysis(
    session: AsyncSession, 
    event_uri: str, 
    country_code: str
) -> CountryEventAnalysis | None:
    """
    삼중 복합 필터(사건, 국가, 날짜)를 기준으로 
    특정 국가의 상세 분석 데이터를 단일 Row로 조회합니다.
    """
    
    stmt = (
        select(CountryEventAnalysis)
        .where(
            CountryEventAnalysis.event_uri == event_uri,
            # 대소문자 불일치로 인한 쿼리 누락 방지를 위해 소문자 보정 적용
            CountryEventAnalysis.country_code == country_code.lower()
        )
    )
    
    result = await session.execute(stmt)
    print(f"result:{result}")
    # 한 건만 정확히 가져오거나 없으면 None 리턴
    return result.scalar_one_or_none()

async def get_all_country_analyses_by_event(db, event_uri: str):
    """
    특정 사건(event_uri)에 대해 파이프라인이 생성하여 저장해 둔 
    모든 국가별 정세 분석 리포트 행(Row)들을 일괄 조회합니다.
    """
    stmt = select(CountryEventAnalysis).where(CountryEventAnalysis.event_uri == event_uri)
    result = await db.execute(stmt)
    
    # 레코드 객체 리스트 반환 (.scalars().all() 활용)
    return result.scalars().all()