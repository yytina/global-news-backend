-- 1. 기존 데이터 백업 없이 컬럼 타입을 무제한 TEXT 기반의 JSONB로 강제 형변환합니다.
ALTER TABLE events 
  ALTER COLUMN all_titles TYPE JSONB USING all_titles::jsonb,
  ALTER COLUMN all_summaries TYPE JSONB USING all_summaries::jsonb;

-- 2. 혹시 모르니 국가별 분석 카운트 컬럼도 함께 안전하게 확보합니다.
ALTER TABLE events 
  ALTER COLUMN article_counts TYPE JSONB USING article_counts::jsonb,
  ALTER COLUMN target_country_uris TYPE JSONB USING target_country_uris::jsonb;