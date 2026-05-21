from datetime import datetime, timezone
import operator
from typing import Annotated, List, TypedDict
import json

from sqlalchemy import func
from constants import COUNTRY_MAP
from database import AsyncSessionLocal
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
import crud

from langgraph.graph import StateGraph, START, END
from prompts import article_analysis_prompt, country_analysis_prompt

load_dotenv()

model = ChatOpenAI(model="gpt-4o")

# ==========================================
# 1. State & Schema 정의 (target_date 방어선 구축)
# ==========================================
class GraphState(TypedDict):
    event_uri: str
    target_date: str  # 🎯 [핵심] State 내에 날짜 타입을 명시하여 데이터 유실 원천 차단
    event_info: dict  
    articles: List[dict]  
    current_article: dict 
    analysis_results: Annotated[list, operator.add]
    country_analysis_results: list

def continue_to_analysis(state: GraphState):
    return [
        Send("analyzer", {"current_article": article, "event_info": state["event_info"]})
        for article in state["articles"]
    ]

# ==========================================
# 2. Nodes (기능 단위 함수들)
# ==========================================
async def node_load_articles(state: GraphState):
    event_uri = state["event_uri"]
    # 최초 인입된 target_date 확보
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
            "target_date": target_date  # State에 유지
        }

async def node_analyze_article(state: GraphState):
    article = state.get("current_article") or state.get("article")
    event = state.get("event_info")
    
    if not article:
        return {"analysis_results": []}

    def safe_get(obj, key, default=None):
        if isinstance(obj, dict): return obj.get(key, default)
        return getattr(obj, key, default)

    # 1. URL 정보 추출 추가
    article_uri = safe_get(article, "uri", "Unknown") 
    article_url = safe_get(article, "url", "Unknown") # 기사 원문 URL
    country_uri = safe_get(article, "country_uri")
    title = safe_get(article, "title", "No Title")
    body = safe_get(article, "body", "")

    country_code = COUNTRY_MAP.get(country_uri, "unknown")

    try:
        chain = article_analysis_prompt | model | StrOutputParser()
        
        # 2. 템플릿에 article_url 주입
        raw_response = await chain.ainvoke({
            "event_title_main": event.get("title_main", "No Title"),
            "event_summary_main": event.get("summary_main", ""),
            "article_title": title,
            "article_url": article_url, 
            "article_body": body
        })
        
        cleaned_json = raw_response.replace("```json", "").replace("```", "").strip()
        response = json.loads(cleaned_json)
        
        # 3. 데이터 구조 보강
        response["analysis_status"] = "COMPLETED"
        
        return {
            "analysis_results": [{
                "raw_analysis": response, 
                "target_uri": article_uri,
                "source_identity": response.get("source_identity", "Unknown"), # 분석 결과에서 추출
                "country_code": country_code
            }]
        }
    except Exception as e:
        print(f"❌ 기사 분석 중 에러 (URI: {article_uri}): {e}")
        return {"analysis_results": []}

async def node_analyze_country(state: GraphState):
    results = state.get("analysis_results", [])
    event = state.get("event_info") or {}
    target_date = state.get("target_date")  # 🎯 상위 State에서 날짜 완벽 접수
    
    from langchain_core.output_parsers import JsonOutputParser
    chain = country_analysis_prompt | model | JsonOutputParser()

    articles_by_country = {}
    for res in results:
        code = res.get("country_code")
        if code and code != "unknown":
            if code not in articles_by_country:
                articles_by_country[code] = []
            articles_by_country[code].append(res.get("raw_analysis", {}))

    country_perspectives = []
    for country_code, analyses in articles_by_country.items():
        try:
            response = await chain.ainvoke({
                "event_title_main": event.get("title_main", "No Title"),
                "event_summary_main": event.get("summary_main", "No Summary"),
                "country_name": country_code.upper(), 
                "country_code": country_code,
                "aggregated_article_analyses": str(analyses)[:15000]
            })
            response["country_code"] = country_code
            country_perspectives.append(response)
            print(f"✅ {country_code} 국가 LLM 분석 완료")
        except Exception as e:
            print(f"❌ {country_code} 국가 분석 중 에러: {e}")

    print(f"DEBUG: 최종 생성된 리포트 수: {len(country_perspectives)}")
    
    return {
        "country_analysis_results": country_perspectives,
        "target_date": target_date  # 🎯 다음 save 노드로 날짜 토스 보장
    }

async def node_save_results(state: dict):
    from sqlalchemy import update, select, func
    from models import Article, Event
    
    target_date_str = state.get("target_date")
    event_uri = state.get("event_uri")
    country_results = state.get("country_analysis_results", [])
    analysis_results = state.get("analysis_results", []) 
    
    print(f"📊 DEBUG - 최종 저장 노드 진입 (Event: {event_uri}, 날짜 변수 상태: {target_date_str})")

    # 1. 개별 기사 분석 결과 저장
    if analysis_results:
        async with AsyncSessionLocal() as session:
            try:
                for res in analysis_results:
                    uri = res.get("target_uri") or res.get("uri")
                    raw = res.get("raw_analysis", {})
                    
                    score_sent = raw.get("score_sentiment", {}).get("score", 0.0) if isinstance(raw.get("score_sentiment"), dict) else raw.get("score_sentiment", 0.0)
                    score_obje = raw.get("score_objectivity", {}).get("score", 0.0) if isinstance(raw.get("score_objectivity"), dict) else raw.get("score_objectivity", 0.0)
                    score_urge = raw.get("score_urgency", {}).get("score", 0.0) if isinstance(raw.get("score_urgency"), dict) else raw.get("score_urgency", 0.0)
                    score_cred = raw.get("score_credibility", {}).get("score", 0.0) if isinstance(raw.get("score_credibility"), dict) else raw.get("score_credibility", 0.0)
                    score_sens = raw.get("score_sensationalism", {}).get("score", 0.0) if isinstance(raw.get("score_sensationalism"), dict) else raw.get("score_sensationalism", 0.0)
                    summary_en = raw.get("analysis_summary_en") or raw.get("article_summary_en") or raw.get("summary_en") or ""
                    summary_kr = raw.get("analysis_summary_kr")
                    
                    await session.execute(
                        update(Article)
                        .where(Article.uri == uri)
                        .values({
                            "score_sentiment": score_sent,
                            "score_objectivity": score_obje,
                            "score_urgency": score_urge,
                            "score_credibility": score_cred,
                            "score_sensationalism": score_sens,
                            "analysis_summary_en": summary_en, 
                            "analysis_summary_kr": summary_kr, 
                            "analysis_status": "COMPLETED",
                            "analyzed_at": func.now()
                        })
                    )
                await session.commit()
                print(f"✅ {len(analysis_results)}개 기사 분석 데이터 저장 완료!")
            except Exception as e:
                await session.rollback()
                print(f"❌ 개별 기사 저장 실패: {e}")

    # 2. 국가 분석 데이터 저장 (테스트 코드 규격 검증 완료본)
    if country_results and target_date_str:
        async with AsyncSessionLocal() as session:
            try:
                cleaned_results = []
                for item in country_results:
                    if isinstance(item, str):
                        try: cleaned_results.append(json.loads(item))
                        except json.JSONDecodeError: continue
                    elif isinstance(item, dict):
                        cleaned_results.append(item)
                
                print(f"🔄 {len(cleaned_results)}개 국가 분석 DB 적재 시도 중...")
                await crud.upsert_country_analysis(session, event_uri, cleaned_results, target_date_str)
                await session.commit()
                print(f"🏆 country_event_analysis 테이블 최종 커밋 완료! (날짜: {target_date_str})")
            except Exception as e:
                await session.rollback()
                print(f"❌ 국가 분석 저장 실패: {e}")
    else:
        print(f"⚠️ 스킵됨: country_results 존재여부({bool(country_results)}), target_date 존재여부({target_date_str})")

    # 3. Event 테이블 평균값 업데이트
    async with AsyncSessionLocal() as session:
        try:
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
                await session.commit()
                print(f"🏆 사건 통합 감정 지수 ({round(final_sentiment, 4)}) 최종 커밋 완료!")
        except Exception as e:
            await session.rollback()
            print(f"❌ Event 테이블 업데이트 실패: {e}")

    return {"final_status": "COMPLETED"}

# ==========================================
# 3. Graph Build & Compile
# ==========================================
from langgraph.types import Send

def create_analysis_graph():
    workflow = StateGraph(GraphState)
    
    workflow.add_node("load", node_load_articles)
    workflow.add_node("analyzer", node_analyze_article)
    workflow.add_node("country_analyzer", node_analyze_country)
    workflow.add_node("save", node_save_results)
    
    workflow.add_edge(START, "load")
    workflow.add_conditional_edges("load", continue_to_analysis, ["analyzer"])
    workflow.add_edge("analyzer", "country_analyzer") 
    workflow.add_edge("country_analyzer", "save")
    workflow.add_edge("save", END)
    
    return workflow.compile()

analysis_app = create_analysis_graph()