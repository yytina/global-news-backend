# =========================
# FastAPI 및 필수 모듈 import
# =========================
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Header, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from logic import calculate_weighted_index
import crud
import schemas
from database import AsyncSessionLocal, get_db
from ingestion_service import run_daily_ingestion
from analysis_graph import create_analysis_graph
from datetime import datetime, timedelta, timezone
from constants import COUNTRY_MAP
import pytz

yesterday = datetime.now(timezone.utc) - timedelta(days=1)
target_date_str = yesterday.strftime('%Y-%m-%d')

analysis_app = create_analysis_graph()

async def run_analysis_pipeline(event_uri: str):
    initial_state = {
        "target_date": target_date_str,
        "event_uri": event_uri,
        "articles": [],
        "analysis_results": [],
        "country_analysis_results": [], # 👈 초기 상태에 추가
        "event_info": {}
    }
    
    print(f"🕵️ 이벤트 {event_uri} 분석 프로세스 시작...")
    final_state = await analysis_app.ainvoke(initial_state)
    
    # 🏁 로그 상세화
    article_count = len(final_state.get('analysis_results', []))
    country_count = len(final_state.get('country_analysis_results', []))
    print(f"🏁 분석 완료! [기사: {article_count}건] [국가 분석: {country_count}개국]")
    
    return final_state

# 1. 백그라운드 스케줄러 함수
async def daily_scheduler():
    seoul_tz = pytz.timezone('Asia/Seoul')
    while True:
        # 한국 시간 기준 현재 시각
        now = datetime.now(seoul_tz)
        
        # 09:05분이 되면 실행
        if now.hour == 9 and now.minute == 1:
            print(f"⏰ [Scheduled Task] 09:01 수집 및 분석 시작!")
            try:
                # 1단계: 수집 실행 (수집된 이벤트 URI 리스트를 반환하도록 ingestion_service 수정 필요)
                event_uris = await run_daily_ingestion() 
                
                if event_uris:
                    print(f"✅ {len(event_uris)}개 이벤트 수집 완료. 분석 파이프라인 가동...")
                    
                    # 2단계: 각 이벤트별로 분석 실행
                    for uri in event_uris:
                        try:
                            await run_analysis_pipeline(uri)
                        except Exception as analysis_err:
                            print(f"❌ 이벤트 {uri} 분석 중 에러: {analysis_err}")
                else:
                    print("ℹ️ 오늘 수집된 새로운 이벤트가 없습니다.")

            except Exception as e:
                print(f"❌ 스케줄러 전체 프로세스 에러: {e}")
            
            await asyncio.sleep(60)  # 중복 실행 방지
        await asyncio.sleep(10)



# 2. FastAPI Lifespan 설정 (서버 시작 시 실행)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 스케줄러를 백그라운드 태스크로 등록
    task = asyncio.create_task(daily_scheduler())
    yield
    # 서버 종료 시 태스크 취소
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://global-news-frontend-xi.vercel.app"
        ], #리액트 서버의 주소 제한
    allow_credentials=True, #쿠키 포함 허용
    allow_methods=["*"], #모든 HTTP 메서드 허용(GET,POST,PUT, DELETE)
    allow_headers=["*"], #모든 header 허용
    expose_headers=["*"], #응답 헤더 노출
)



# =========================
# CORS 설정
# =========================
# ⭐ 변경된 부분: 배포 환경에 맞는 CORS 설정
# 배포 후 Vercel 주소가 확정되면 여기에 추가해야 합니다.
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:5173",
#         "https://react-deployment-nu-teal.vercel.app" # 한글 주석: 프론트엔드 배포 주소를 추가하여 CORS 차단을 방지합니다.
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
#     expose_headers=["*"],
# )


# =========================
# EVENTS
# =========================
@app.get("/events/top", response_model=List[schemas.EventSummary])
async def get_top_events(
    date: Optional[str] = Query(target_date_str, description="date"),
    number: int = Query(3, description="number"),
    db: AsyncSessionLocal = Depends(get_db)
):
    """
    특정 날짜(기본: 어제)의 기사 수 기준 상위 N개 이벤트를 요약본으로 가져옵니다.
    """
    events = await crud.get_top_daily_events(db, limit=number, target_date=date)
    
    return events

@app.get("/events/{event_uri}/map-data")
async def get_event_map_data(event_uri: str, db: AsyncSessionLocal = Depends(get_db)):
    result = await crud.get_event_analysis_package(db, event_uri)
    
    if result["status"] != "SUCCESS":
        return result

    event = result["event"] 
    analyzed_articles = result["data"]
    print("analyzed_articles")
    print(len(analyzed_articles))
    # 💡 [Gem's Logic] all_titles JSON에서 한국어 제목 추출
    # all_titles는 dict 형태이므로 .get()으로 안전하게 접근합니다.
    all_titles = event.all_titles or {}
    title_kr = all_titles.get("kor") or all_titles.get("kor_kr") or event.title_main
    
    # 국가별 그룹화 및 가중치 계산
    country_groups = {}
    for a in analyzed_articles:
        country_groups.setdefault(a.country_uri, []).append(a)
    
    map_data = []
    for country_uri, articles in country_groups.items():
        print(country_uri)
        weighted_indices = calculate_weighted_index(articles[:5])
        if weighted_indices:
            map_data.append({
                "country_uri": country_uri,
                "country_code": COUNTRY_MAP.get(country_uri, "unknown"), # 👈 추가!
                "sentiment": round(weighted_indices["sentiment"], 4),
                "all_indices": weighted_indices
            })
    print(map_data)
            
    return {
        "status": "SUCCESS",
        "event_uri": event.uri,
        "title_main": event.title_main,
        "title_kr": title_kr,  # ✅ JSON에서 동적으로 가져온 한국어 제목
        "map_data": map_data
    }

    
# 1. response_model에서 List[]를 완전히 제거하여 단일 객체 스키마로 변경합니다.
@app.get("/events/{event_uri}/countries/{country_code}", response_model=schemas.CountryAnalysisResponse)
async def get_country_event_analysis(
    event_uri: str,
    country_code: str,
    date: Optional[str] = Query(target_date_str, description="date"),
    db: AsyncSessionLocal = Depends(get_db)
):
    result = await crud.get_event_country_analysis(db, event_uri, country_code, date)
    
    # 🎯 데이터가 존재하지 않을 때 (None일 때) 404 에러를 명시적으로 반환합니다.
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404, 
            detail=f"Analysis for country '{country_code}' on date '{date}' not found."
        )
        
    return result

@app.get(
    "/events/{event_uri}/countries/{country_code}/articles", 
    response_model=schemas.CountryArticlesResponse
)
async def get_article_analysis_for_event_country(
    event_uri: str,
    country_code: str,
    db: AsyncSessionLocal = Depends(get_db)
):
    # 1. DB에서 조건에 맞는 기사 객체 리스트 조회
    db_articles = await crud.get_articles_by_event_and_country(db, event_uri, country_code)
    event = await crud.get_event_by_uri(db, event_uri)
    event_title = event.title_main if event else event_uri.replace("-", " ").capitalize()
    # 2. Pydantic 스키마 규격에 맞춰 데이터 리셰이핑(Reshaping)
    return {
        "event_uri": event_uri,
        "event_title":event_title, 
        "country_code": country_code,
        "total_count": len(db_articles),
        "articles": db_articles  # SQLAlchemy 모델 객체 리스트가 자동 변환됩니다.
    }



@app.post("/admin/run-pipeline")
async def trigger_full_pipeline():
    """수동으로 수집 및 분석 파이프라인 전체를 즉시 실행합니다."""
    # 백그라운드 태스크로 돌려야 API 응답이 끊기지 않습니다.
    async def run():
        # uris = await run_daily_ingestion()
        # uris=["spa-4195449", "eng-11650549", "eng-11650080"]
        # uris=["eng-11651919"]
        # spa-4197658
        uris=["eng-11651919"]
        for uri in uris:
            await run_analysis_pipeline(uri)
            
    asyncio.create_task(run())
    return {"status": "Processing", "message": "수집 및 분석이 백그라운드에서 시작되었습니다."}

@app.get("/keep-alive")
def keep_alive():
    return {"message": "Server is alive"}