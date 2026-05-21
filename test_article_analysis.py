import asyncio
from analysis_graph import node_analyze_article, node_save_results
from database import AsyncSessionLocal
import crud

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# .env 파일에 정의된 변수들을 시스템 환경 변수로 로드합니다.
load_dotenv()

print("====================================")
print(f"📡 현재 스크립트가 바라보는 DB URL: {os.getenv('DATABASE_URL')}")
print("====================================")

async def main():
    async with AsyncSessionLocal() as session:
        # 1. DB에서 분석 안 된 기사 하나 가져오기
        # article = await crud.get_one_pending_article(session) 
        article_uri="2026-05-1170654486"
        article = await crud.get_article_by_uri(session, article_uri=article_uri)
        print("Article")
        print(article)
        event = await crud.get_event_by_uri(session, article.event_uri)
        print("event")
        print(event)
        print(event.uri)
        
        # 2. 가상의 State 생성
        state = {
            "current_article": {"uri": article.uri, "title": article.title, "body": article.body},
            "event_info": {"title_main": event.title_main, "summary_main": event.summary_main},
            "analysis_results": []
        }
        
        # 3. 분석 노드만 단독 실행
        print(f"🚀 '{article.title}' 분석 시작...")
        result = await node_analyze_article(state)
        
        # 4. 결과 확인
        print("✅ 분석 완료!")
        import json
        if result.get("analysis_results"):
            print(json.dumps(result["analysis_results"][0], indent=2, ensure_ascii=False))
        else:
            print("❌ 분석 결과가 비어 있습니다. node_analyze_article 내부 로직을 확인하세요.")

        final_state = {
            "analysis_results": result["analysis_results"],
            "event_uri": article.event_uri
        }

        print("💾 DB 저장 시작...")
        save_result = await node_save_results(final_state)
        print(f"🏁 최종 상태: {save_result['final_status']}")

        

if __name__ == "__main__":
    asyncio.run(main())