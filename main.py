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
from langchain_core.runnables import RunnableConfig
import traceback

config = RunnableConfig(configurable={"thread_id": "test-run-1"})

yesterday = datetime.now(timezone.utc) - timedelta(days=1)
target_date_str = yesterday.strftime('%Y-%m-%d')

analysis_app = create_analysis_graph()

from fastapi import Security
from fastapi.security.api_key import APIKeyHeader
import os
from dotenv import load_dotenv
load_dotenv()

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")
API_KEY_NAME = "X-Admin-Token"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

async def verify_admin_token(api_key: str = Security(api_key_header)):
    if api_key != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=403, 
            detail="Forbidden: Invalid Admin Token"
        )
    return api_key

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
    final_state = await analysis_app.ainvoke(initial_state,config=config)
    
    # 🏁 로그 상세화
    article_count = len(final_state.get('analysis_results', []))
    country_count = len(final_state.get('country_analysis_results', []))
    print(f"🏁 분석 완료! [기사: {article_count}건] [국가 분석: {country_count}개국]")
    
    return final_state

# 1. 백그라운드 스케줄러 함수
async def daily_scheduler():
    seoul_tz = pytz.timezone('Asia/Seoul')
    while True:
        now = datetime.now(seoul_tz)
        
        # 09:05분이 되면 실행 (현재 테스트 타임 11:15로 세팅됨)
        if now.hour == 11 and now.minute == 20:
            print(f"⏰ [Scheduled Task] 11:20 수집 및 분석 시작!")
            try:
                # 1단계: 수집 실행
                event_uris = await run_daily_ingestion() 
                print(f"🔍 DEBUG: run_daily_ingestion 반환 결과 -> {event_uris}") # 수집기 결과 추적용
                
                if event_uris:
                    print(f"✅ {len(event_uris)}개 이벤트 수집 완료. 분석 파이프라인 가동...")
                    
                    for uri in event_uris:
                        try:
                            await run_analysis_pipeline(uri)
                        except Exception as analysis_err:
                            print(f"❌ 이벤트 {uri} 분석 중 에러 발생!")
                            traceback.print_exc() # 🎯 [핵심] 상세 스택 트레이스백 강제 출력
                else:
                    print("ℹ️ 오늘 수집된 새로운 이벤트가 없습니다.")

            except Exception as e:
                print(f"❌ 스케줄러 전체 프로세스 치명적 에러:")
                traceback.print_exc() # 🎯 [핵심] 상위 스케줄러가 터진 위치와 라인을 정확히 추적
            
            await asyncio.sleep(60)
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

@app.head("/keep-alive", status_code=200)
def keep_alive():
    return Response()

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
    all_titles = event.all_titles or {}
    title_kr = all_titles.get("kor") or all_titles.get("kor_kr") or event.title_main
    
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
        "epicenter":{
            "country_uri": event.epicenter_country_uri,
            "country_code": COUNTRY_MAP.get(event.epicenter_country_uri, "unknown")
        },
        "title_main": event.title_main,
        "title_kr": title_kr,
        "map_data": map_data
    }

    
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

    db_articles = await crud.get_articles_by_event_and_country(db, event_uri, country_code)
    event = await crud.get_event_by_uri(db, event_uri)
    event_title = event.title_main if event else event_uri.replace("-", " ").capitalize()

    return {
        "event_uri": event_uri,
        "event_title":event_title, 
        "country_code": country_code,
        "total_count": len(db_articles),
        "articles": db_articles  
    }

@app.post("/admin/run-pipeline")
async def trigger_full_pipeline(
    ingestion: bool = Query(True, description="True면 수집 후 분석, False면 수집 스킵 후 분석만 실행"),
    admin_token: str = Depends(verify_admin_token)
):
    """
    인증된 관리자만 수동으로 수집 및 분석 파이프라인을 즉시 실행합니다.
    ingestion=False인 경우, 수집기를 거치지 않고 바로 기존 데이터 분석으로 진입합니다.
    """
    async def run():
        seoul_tz = pytz.timezone('Asia/Seoul')
        now = datetime.now(seoul_tz)
        yesterday = now - timedelta(days=1)
        dynamic_target_date = yesterday.strftime('%Y-%m-%d')
        
        event_uris = []

        if ingestion:
            print("🚀 [수동 트리거] 데이터 수집(Ingestion) 시작...")
            event_uris = await run_daily_ingestion()
        else:
            print("ℹ️ [수동 트리거] 수집 단계를 스킵합니다. 기존 소스 데이터를 기반으로 분석만 수행합니다.")
            # 🎯 [필독] 수집을 스킵할 경우, 기존 DB에서 분석 대상(예: PENDING 상태)인 
            # 이벤트 URI 리스트를 동적으로 가져오는 레포지토리 로직이 필요할 수 있습니다.
            # 예: event_uris = await crud.get_pending_event_uris(db, dynamic_target_date)
            # 현재는 디버깅을 위해 하드코딩된 테스트 URI나 기존 조회 로직을 연동해야 합니다.
            
        if event_uris:
            print(f"🚀 [수동 트리거] {len(event_uris)}개 이벤트 분석 가동 ({dynamic_target_date})...")
            for uri in event_uris:
                try:
                    await run_analysis_pipeline(uri, dynamic_target_date)
                except Exception as analysis_err:
                    print(f"❌ 이벤트 {uri} 분석 중 에러: {analysis_err}")
        else:
            print("ℹ️ [수동 트리거] 분석할 이벤트 URI가 존재하지 않아 파이프라인을 종료합니다.")
            
    asyncio.create_task(run())
    return {
        "status": "Processing", 
        "message": f"인증 완료. 백그라운드 태스크가 시작되었습니다. (수집 여부: {ingestion})"
    }
