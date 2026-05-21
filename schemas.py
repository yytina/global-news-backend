from pydantic import BaseModel, ConfigDict, HttpUrl
from typing import List, Optional, Dict
from datetime import date

# --- Event 관련 ---
class EventCreate(BaseModel):
    uri: str
    title_main: str
    summary_main: str
    all_titles: Dict[str, str]
    all_summaries: Dict[str, str]
    size: int
    article_counts: Dict[str, int]
    epicenter_country_uri: Optional[str] = None
    target_country_uris: List[str]
    date: date

# --- 이벤트 조회의 기본 단위 ---
class EventDisplay(BaseModel):
    uri: str
    title_main: str
    summary_main: str
    
    # 분석에 중요한 핵심 지표들
    size: int
    social_score: int
    
    # 국가 관련 정보 (우리가 정리한 이름들)
    epicenter_country_uri: Optional[str]
    target_country_uris: List[str]
    article_counts: Dict[str, int]
    
    # 날짜 정보
    event_date: date        # 데이터 기준일 (어제 날짜 등)

    
    # SQLAlchemy 모델 객체를 이 스키마로 바로 변환하기 위한 설정
    model_config = ConfigDict(from_attributes=True)

# --- (선택) 목록 조회 시 더 가벼운 정보를 원할 때 ---
class EventSummary(BaseModel):
    uri: str
    title_main: str
    date: date
    size: int
    avg_sentiment: float

    model_config = ConfigDict(from_attributes=True)
# --- Article 관련 ---
class ArticleSource(BaseModel):
    uri: str
    date: date
    event_uri: str
    country_uri: str
    lang_code: str
    title: str
    body: str
    url: str

class ScoreDetail(BaseModel):
    score: float
    reasoning: str

class ArticleAnalysisResult(BaseModel):
    score_sentiment: ScoreDetail
    score_objectivity: ScoreDetail
    score_urgency: ScoreDetail
    score_credibility: ScoreDetail
    score_sensationalism: ScoreDetail
    analysis_summary_en: str
    analysis_summary_kr: str
    analysis_status: str = "COMPLETED"

from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import date

# 1. 개별 기사의 원문 정보와 분석 지표를 하나로 묶는 스키마
class ArticleDetailWithAnalysis(BaseModel):
    uri: str
    date: date
    url: Optional[str] = None
    title: Optional[str] = None
    lang_code: str
    
    # 분석 상태 및 시간
    analysis_status: str
    
    # 5대 지표 (기존 데이터가 점수만 들어가 있으므로 float로 매핑하거나, 
    # 만약 정밀 reasoning까지 포함된 구조라면 기존 ScoreDetail을 사용하세요. 
    # 여기서는 현재 DB 컬럼 구조에 맞춰 float로 설계합니다.)
    score_sentiment: Optional[float] = 0.0
    score_objectivity: Optional[float] = 0.0
    score_urgency: Optional[float] = 0.0
    score_credibility: Optional[float] = 0.0
    score_sensationalism: Optional[float] = 0.0
    
    # 🎯 추가된 국문/영문 요약 필드
    analysis_summary_en: Optional[str] = ""
    analysis_summary_kr: Optional[str] = ""

    model_config = ConfigDict(from_attributes=True)

# 2. 🎯 최종 API가 반환할 리스트 컨테이너 스키마
class CountryArticlesResponse(BaseModel):
    event_uri: str
    event_title: str
    country_code: str
    total_count: int
    articles: List[ArticleDetailWithAnalysis]  # 해당 국가 기사들의 배열


from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CountryAnalysisResponse(BaseModel):
    date: date
    event_uri: str
    country_code: str
    score_sentiment: float
    score_objectivity: float
    score_urgency: float
    score_credibility: float
    score_sensationalism: float
    
    consensus_rate: float
    national_interest: str
    strategic_frame: str
    
    analysis_summary_en: str
    analysis_summary_kr: str

    class Config:
        from_attributes = True