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
    analysis_status: str = "COMPLETED"


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