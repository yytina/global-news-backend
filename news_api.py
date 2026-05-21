from fastapi import FastAPI, Depends, HTTPException, Query, Header, Response, Cookie
from datetime import datetime, timedelta, timezone
import httpx
import time
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()


# ⭐ 변경된 부분: MariaDB URL에서 Supabase PostgreSQL URL로 교체
# 보안을 위해 환경변수 사용을 권장하며, 비밀번호 부분은 실제 비밀번호로 채워야 합니다.
NEWS_API_KEY = os.getenv("NEWS_API_KEY")


app = FastAPI()
today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
yesterday_utc = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

async def get_refined_top3_events():
    # 1. 일단 5개를 가져와서 후보군 확보
    url = "https://eventregistry.org/api/v1/event/getEvents"
    payload = {
        "resultType": "events",
        "dateStart": yesterday_utc,
        "dateEnd": today_utc,
        "minArticlesInEvent": 50,
        "eventsSortBy": "size",
        "eventsCount": 5,        
        "apiKey": NEWS_API_KEY
    }


    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        all_events = response.json().get("events", {}).get("results", [])


    # 2. '이상한 이슈' 제거 필터링 (최대 3개 추출)
    refined_events = []
    for ev in all_events:
        article_counts = ev.get('articleCounts', {})


        # 필터 1: 언어 다양성 검증 (최소 2개 이상의 언어권 보도)
        if len(article_counts.keys()) < 2:
            continue


        refined_events.append(ev)
        if len(refined_events) == 3: # 최대 3개까지만 확보
            break


    return refined_events

async def get_articles_by_event_and_location(
        event_uri: str, location_uri: str, count: int = 5
    ):
    # 1. 일단 5개를 가져와서 후보군 확보
    url = "https://eventregistry.org/api/v1/event/getEvent"
    payload = {
        "action": "getArticles",
        "eventUri": event_uri,
        "resultType": "articles",
        "dateStart": yesterday_utc,
        "dateEnd": yesterday_utc,
        "apiKey": NEWS_API_KEY,
        "sourceLocationUri": location_uri,
        "articlesSortBy": "rel",
        "articlesCount": 5
    }


    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        articles = response.json().get(event_uri, {}).get("articles", {}).get("results", [])
    print(f"📍 Event URI: {event_uri}, Location URI: {location_uri}, Retrieved Articles: {len(articles)}")  # 디버깅용 출력
    return [{**art, 'country_uri': location_uri} for art in articles]

def get_yesterday_utc():
    return yesterday_utc
def get_event_epicenter_wiki(event_data):
  location_data = event_data.get('location', {})
  if not location_data:
      print("⚠️ 이벤트 데이터에 위치 정보가 포함되어 있지 않습니다.")
      print(f"📍 Event Data: {event_data.get('title', {}).get('eng')}")  # 디버깅용 출력
      return None
  country_name = location_data.get('country', {}).get('label', {}).get('eng')
  wiki_url=None
  # 2. 위키피디아 URL 생성
  if country_name:
      # 위키피디아는 공백을 '_'로 처리하므로 replace가 필요합니다.
      wiki_keyword = country_name.replace(" ", "_")
      wiki_url = f"https://en.wikipedia.org/wiki/{wiki_keyword}"
  else:
      print("⚠️ 국가 정보가 데이터에 포함되어 있지 않습니다.")
  return wiki_url


def get_target_country_uris(article_counts):
  # 1. 고정 분석 국가 (Fixed Core)
  fixed_core_uris = [
      "http://en.wikipedia.org/wiki/United_States",
      "https://en.wikipedia.org/wiki/United_Kingdom",
      "https://en.wikipedia.org/wiki/China",
      "http://en.wikipedia.org/wiki/South_Korea",
      "https://en.wikipedia.org/wiki/Japan"
  ]


  # 중복 체크를 위한 고정 국가 이름 집합
  core_names = {uri.split('/')[-1] for uri in fixed_core_uris}


  # 2. 보도량 기준 설정 (10건 이상)
  THRESHOLD = 10


  # 3. 언어별 대표 국가 매핑 (ISO 639-2 -> Wiki Name)
  lang_to_wiki = {
      'eng': 'United_States', 'spa': 'Spain', 'zho': 'China',
      'por': 'Brazil', 'fra': 'France', 'deu': 'Germany',
      'tur': 'Turkey', 'ita': 'Italy', 'hrv': 'Croatia',
      'slv': 'Slovenia', 'cat': 'Spain', # 카탈루냐어는 스페인으로 매핑하거나 생략 가능
      'rus': 'Russia',
      'srp': 'Serbia'
  }


  # 5. 필터링 및 리스트 생성
  final_target_uris = list(fixed_core_uris)


  print(f"📊 Threshold ({THRESHOLD}) 적용 결과:")
  for lang, count in article_counts.items():
      if count >= THRESHOLD:
          wiki_name = lang_to_wiki.get(lang)
          if wiki_name and wiki_name not in core_names:
              new_uri = f"https://en.wikipedia.org/wiki/{wiki_name}"
              final_target_uris.append(new_uri)
              core_names.add(wiki_name)
              print(f"✅ 추가됨: {wiki_name} ({count}건)")
      else:
          print(f"➖ 제외됨: {lang} ({count}건)")


  print(f"\n🌍 최종 분석 대상 국가: 총 {len(final_target_uris)}개")
  return final_target_uris


def map_iso_to_wiki_uri(country_code):
    # ISO 2-letter 코드를 위키피디아 URI로 매핑
    iso_to_wiki = {
        "US": "http://en.wikipedia.org/wiki/United_States",
        "GB": "http://en.wikipedia.org/wiki/United_Kingdom",
        "CN": "http://en.wikipedia.org/wiki/China",
        "KR": "http://en.wikipedia.org/wiki/South_Korea",
        "JP": "http://en.wikipedia.org/wiki/Japan"
    }
    return iso_to_wiki.get(country_code)
