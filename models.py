# models.py
from sqlalchemy import Column, Date, Float, String, Integer, Text, ForeignKey, DateTime, func, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base

class Event(Base):
    __tablename__ = "events"

    uri = Column(String, primary_key=True)
    date = Column(Date, nullable=False)
    title_main = Column(String, nullable=False)
    summary_main = Column(Text)
    all_titles = Column(JSONB)       # 다국어 제목들 저장
    all_summaries = Column(JSONB)    # 다국어 요약들 저장
    size = Column(Integer)
    article_counts = Column(JSONB)
    epicenter_country_uri = Column(String)
    target_country_uris = Column(JSONB, default=[]) # 리스트 형태로 저장됩니다.
    created_at = Column(DateTime, default=datetime.utcnow())
    analysis_status = Column(String(20), default="PENDING") # 추가
    avg_sentiment = Column(Float, default=0.0, nullable=True)
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now())

    # 1:N 관계 설정 (Event 하나에 여러 Article)
    articles = relationship("Article", back_populates="event", cascade="all, delete")

class Article(Base):
    __tablename__ = "articles"

    uri = Column(String, primary_key=True)
    date = Column(Date, nullable=False)
    event_uri = Column(String, ForeignKey("events.uri", ondelete="CASCADE"))
    country_uri = Column(String, nullable=False)
    lang_code = Column(String(10), nullable=False)
    title = Column(Text)
    body = Column(Text)
    url = Column(Text)
    
    # --- 여기서부터 추가/수정된 부분 ---
    analysis_status = Column(String(20), default="PENDING")
    
    # 5대 지표 컬럼 (DB의 float8과 매칭)
    score_sentiment = Column(Float)
    score_objectivity = Column(Float)
    score_urgency = Column(Float)
    score_credibility = Column(Float)
    score_sensationalism = Column(Float)
    
    # 요약 및 분석 시간
    analysis_summary_en = Column(Text)
    analysis_summary_kr = Column(Text)
    
    analyzed_at = Column(DateTime)
    # ------------------------------

    created_at = Column(DateTime, default=datetime.utcnow())

    event = relationship("Event", back_populates="articles")

from database import Base
from sqlalchemy import Column, String, Float, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

class CountryEventAnalysis(Base):
    __tablename__ = "country_event_analysis"

    # id는 자동생성 PK, event와 country 조합으로 유니크 제약조건 추가
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    event_uri = Column(String, ForeignKey("events.uri", ondelete="CASCADE"), nullable=False)
    country_code = Column(String(5), nullable=False)  # 'kr', 'us', 'fr' 등

    # 5대 지표 (Reasoning은 나중에 모달에서 보여주기 위해 Text로 저장)
    score_sentiment = Column(Float)
    score_objectivity = Column(Float)
    score_urgency = Column(Float)
    score_credibility = Column(Float)
    score_sensationalism = Column(Float)
    
    # 국가 전략 분석 필드
    consensus_rate = Column(Float)
    national_interest = Column(Text)
    strategic_frame = Column(Text)
    
    # 요약 (한/영)
    analysis_summary_en = Column(Text)
    analysis_summary_kr = Column(Text)
    
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    # 동일한 이벤트에 대해 한 국가당 하나의 분석만 존재하도록 설정
    __table_args__ = (UniqueConstraint('event_uri', 'country_code', 'date', name='_event_country_date_uc'),)