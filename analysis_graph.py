from datetime import datetime, timezone
import operator
from typing import Annotated, List, TypedDict
import json
import asyncio  # 🎯 비동기 세마포어 제어를 위해 필수 추가

from sqlalchemy import func, update, select
from constants import COUNTRY_MAP
from database import AsyncSessionLocal
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
import crud

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send  # 🎯 명시적 임포트 배치
from langsmith import traceable
from prompts import article_analysis_prompt, country_analysis_prompt
from models import Article, Event

load_dotenv()

# 인프라 비용 및 메모리 방어를 위한 모델 선언
model = ChatOpenAI(model="gpt-4o", temperature=0.2)

# Render.com 무료 티어(512MB RAM) 보호를 위한 가용성 방어선
# 동시에 딱 2개의 대형 LLM 연산/국가 분석만 큐에 진입하도록 제한
SEMAPHORE = asyncio.Semaphore(2)

# ==========================================
# 1. State & Schema 정의
# ==========================================
class GraphState(TypedDict):
    event_uri: str
    target_date: str  
    event_info: dict  
    articles: List[dict]  
    current_article: dict 
    # Annotated[list, operator.add] 는 병렬 Map-Reduce 수렴 시 자동으로 리스트를 병합해줍니다.
    analysis_results: Annotated[list, operator.add]
    country_analysis_results: list

# 개별 기사 분석으로 라우팅하는 Map 분기 함수
def continue_to_analysis(state: GraphState):
    return [
        Send("analyzer", {
            "current_article": article, 
            "event_info": state["event_info"],
            "target_date": state.get("target_date"),
            "event_uri": state.get("event_uri")
        })
        for article in state["articles"]
    ]

# ==========================================
# 2. Nodes (안정성 및 트랜잭션 최적화 버전)
# ==========================================
async def node_load_articles(state: GraphState):
    event_uri = state["event_uri"]
    target_date = state.get("target_date") 
    
    async with AsyncSessionLocal() as session:
        event = await crud.get_event_by_uri(session, event_uri)
        if not event:
            print(f"❌ 이벤트를 찾을 수 없음: {event_uri}")
            return state

        event_info = {
            "uri": event.uri,
            "title_main": event.title_main, 
            "summary_main": event.summary_main
        }
        articles = await crud.get_articles_by_event(session, event_uri)
        
        return {
            "articles": articles,
            "event_info": event_info,
            "target_date": target_date  
        }

@traceable(name="Article Analysis Agent")
async def node_analyze_article(state: GraphState):
    article = state.get("current_article")
    event = state.get("event_info")
    
    if not article:
        return {"analysis_results": []}

    # 🎯 [핵심 개선] ORM 객체(Attribute)와 dict(Key) 형태 모두 대응 가능한 방어적 추출 함수 정의
    def safe_get(obj, key, default=None):
        if isinstance(obj, dict): 
            return obj.get(key, default)
        return getattr(obj, key, default)

    # safe_get을 사용하여 ORM 모델 인스턴스에서 안전하게 속성 값 추출
    article_uri = safe_get(article, "uri", "Unknown") 
    article_url = safe_get(article, "url", "Unknown") 
    country_uri = safe_get(article, "country_uri")
    title = safe_get(article, "title", "No Title")
    body = safe_get(article, "body", "")

    country_code = COUNTRY_MAP.get(country_uri, "unknown")

    # 가용성 확보를 위한 세마포어 가드 작동
    async with SEMAPHORE:
        try:
            chain = article_analysis_prompt | model | StrOutputParser()
            raw_response = await chain.ainvoke({
                "event_title_main": event.get("title_main", "No Title"),
                "event_summary_main": event.get("summary_main", ""),
                "article_title": title,
                "article_url": article_url, 
                "article_body": body
            })
            
            cleaned_json = raw_response.replace("```json", "").replace("```", "").strip()
            response = json.loads(cleaned_json)
            response["analysis_status"] = "COMPLETED"
            
            return {
                "analysis_results": [{
                    "raw_analysis": response, 
                    "target_uri": article_uri,
                    "source_identity": response.get("source_identity", "Unknown"), 
                    "country_code": country_code
                }]
            }
        except Exception as e:
            print(f"❌ 기사 분석 중 에러 (URI: {article_uri}): {e}")
            return {"analysis_results": []}

@traceable(name="Country Analysis Agent")
async def node_analyze_country(state: GraphState):
    results = state.get("analysis_results", [])
    event = state.get("event_info") or {}
    target_date = state.get("target_date")
    
    from langchain_core.output_parsers import JsonOutputParser
    chain = country_analysis_prompt | model | JsonOutputParser()

    articles_by_country = {}
    for res in results:
        code = res.get("country_code")
        if code and code != "unknown":
            if code not in articles_by_country:
                articles_by_country[code] = []
            articles_by_country[code].append(res.get("raw_analysis", {}))

    # 🎯 [핵심 개선] 개별 국가 분석 태스크를 세마포어 제어 하에 비동기 배치로 처리하여 OOM 완전 차단
    async def analyze_single_country(country_code, analyses):
        async with SEMAPHORE:
            try:
                response = await chain.ainvoke({
                    "event_title_main": event.get("title_main", "No Title"),
                    "event_summary_main": event.get("summary_main", "No Summary"),
                    "country_name": country_code.upper(), 
                    "country_code": country_code,
                    "aggregated_article_analyses": str(analyses)[:12000] # 컨텍스트 상한 최적화
                })
                response["country_code"] = country_code
                print(f"✅ {country_code} 국가 LLM 분석 완료")
                return response
            except Exception as e:
                print(f"❌ {country_code} 국가 분석 중 에러: {e}")
                return None

    # 비동기 태스크 생성 및 가더(gather) 실행
    tasks = [analyze_single_country(code, ans) for code, ans in articles_by_country.items()]
    completed_reports = await asyncio.gather(*tasks)
    country_perspectives = [r for r in completed_reports if r is not None]

    print(f"📊 DEBUG: 최종 생성된 국가 리포트 수: {len(country_perspectives)}")
    
    return {
        "country_analysis_results": country_perspectives,
        "target_date": target_date  
    }

async def node_save_results(state: GraphState):
    target_date_str = state.get("target_date")
    event_uri = state.get("event_uri")
    country_results = state.get("country_analysis_results", [])
    analysis_results = state.get("analysis_results", []) 
    
    print(f"🚀 [SAVE] 최종 저장 트랜잭션 가동 (Event: {event_uri}, Target Date: {target_date_str})")

    # 🎯 [핵심 개선] 세션을 딱 한 번만 열어 모든 테이블(Article, Country, Event)을 단일 트랜잭션으로 처리
    async with AsyncSessionLocal() as session:
        try:
            # 1. 개별 기사 일괄 업데이트
            if analysis_results:
                for res in analysis_results:
                    uri = res.get("target_uri") or res.get("uri")
                    raw = res.get("raw_analysis", {})
                    
                    def extract_score(field):
                        if isinstance(raw.get(field), dict):
                            return raw[field].get("score", 0.0)
                        return raw.get(field, 0.0)

                    await session.execute(
                        update(Article)
                        .where(Article.uri == uri)
                        .values({
                            "score_sentiment": extract_score("score_sentiment"),
                            "score_objectivity": extract_score("score_objectivity"),
                            "score_urgency": extract_score("score_urgency"),
                            "score_credibility": extract_score("score_credibility"),
                            "score_sensationalism": extract_score("score_sensationalism"),
                            "analysis_summary_en": raw.get("analysis_summary_en") or "", 
                            "analysis_summary_kr": raw.get("analysis_summary_kr") or "", 
                            "analysis_status": "COMPLETED",
                            "analyzed_at": func.now()
                        })
                    )
                print(f"✅ {len(analysis_results)}개 기사 분석 데이터 스테이징 완료")

            # 2. 국가별 분석 테이블 적재
            if country_results and target_date_str:
                cleaned_results = [item for item in country_results if isinstance(item, dict)]
                await crud.upsert_country_analysis(session, event_uri, cleaned_results, target_date_str)
                print(f"✅ {len(cleaned_results)}개 국가 분석 데이터 스테이징 완료")

            # 3. 사건 통합 감정 지수 산출 및 Event 테이블 갱신
            stmt = select(Article.score_sentiment).where(
                Article.event_uri == event_uri,
                Article.analysis_status == "COMPLETED"
            )
            res = await session.execute(stmt)
            scores = [row[0] for row in res.all() if row[0] is not None]

            if scores:
                final_sentiment = sum(scores) / len(scores)
                await session.execute(
                    update(Event)
                    .where(Event.uri == event_uri)
                    .values({
                        "avg_sentiment": round(final_sentiment, 4),
                        "updated_at": func.now()
                    })
                )
                print(f"✅ 사건 통합 감정 지수 ({round(final_sentiment, 4)}) 계산 완료")

            # 🔥 [핵심] 여기서 단 한 번 완벽하게 커밋을 침으로써 원자성(Atomicity) 확보 및 유실 방지
            await session.commit()
            print(f"🏆 [SUCCESS] 모든 아티팩트가 Supabase DB에 최종 커밋되었습니다! (Date: {target_date_str})")

        except Exception as e:
            await session.rollback()
            print(f"❌ [ROLLBACK] 데이터 저장 중 예외 발생으로 전체 롤백 처리: {e}")
            raise e

    return {"final_status": "COMPLETED"}

# ==========================================
# 3. Graph Build & Compile (Map-Reduce 아키텍처 정립)
# ==========================================
def create_analysis_graph():
    workflow = StateGraph(GraphState)
    
    workflow.add_node("load", node_load_articles)
    workflow.add_node("analyzer", node_analyze_article)
    workflow.add_node("country_analyzer", node_analyze_country)
    workflow.add_node("save", node_save_results)
    
    workflow.add_edge(START, "load")
    
    # 🎯 [핵심 개선] 엣지 구조 변경: 
    # load에서 각 기사별로 분기(Map)시킨 뒤, 병렬 작업이 끝나면 'country_analyzer' 노드로 수렴(Reduce)하도록 빌드
    workflow.add_conditional_edges("load", continue_to_analysis, ["analyzer"])
    workflow.add_edge("analyzer", "country_analyzer") 
    workflow.add_edge("country_analyzer", "save")
    workflow.add_edge("save", END)
    
    return workflow.compile()

analysis_app = create_analysis_graph()