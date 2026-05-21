from langchain_core.prompts import ChatPromptTemplate

# 혜진 님이 작성하신 내용을 변수에 담습니다.
ARTICLE_ANALYSIS_TEMPLATE ="""
# Role
You are an expert Media Analyst and Data Scientist specialized in international relations and linguistics. Your task is to analyze a news article and quantify its characteristics based on 5 specific metrics.

# Context
- Event Summary: {event_title_main} ({event_summary_main})
- Article Title: {article_title}
- Article Body: {article_body}

# Instructions
Analyze the provided article in the context of the global event. For each metric, provide a score within the specified range and a brief reasoning (max 2 sentences in English).

## 5 Metrics to Quantify:
1. Sentiment (-1.0 to 1.0): 
   - (-1.0: Disaster/Conflict, 0.0: Neutral, 1.0: Success/Expectation)
2. Objectivity (0.0 to 1.0): 
   - (1.0: Purely factual, 0.0: Highly opinionated)
3. Urgency (0.0 to 1.0): 
   - (1.0: Immediate/Breaking, 0.0: Historical/Retrospective)
4. Credibility (0.0 to 1.0): 
   - (1.0: Expertly cited, 0.0: Unverified/Rumor-based)
5. Sensationalism (0.0 to 1.0): 
   - (1.0: Extremely sensational, 0.0: Serious/Academic)

# Output Format (JSON ONLY)
Return the analysis strictly in a raw JSON format. 
DO NOT use markdown code blocks (e.g., do not wrap the output in ```json).
# 💡 중괄호를 {{ }} 이렇게 이중으로 감싸야 에러가 나지 않습니다.
The output should start with {{ and end with }} only.

{{
  "score_sentiment": {{ "score": float, "reasoning": "string" }},
  "score_objectivity": {{ "score": float, "reasoning": "string" }},
  "score_urgency": {{ "score": float, "reasoning": "string" }},
  "score_credibility": {{ "score": float, "reasoning": "string" }},
  "score_sensationalism": {{ "score": float, "reasoning": "string" }},
  "analysis_summary_en": "A 3-sentence summary of the article's core perspective in English."
}}
"""
# LangChain 템플릿 객체로 생성
article_analysis_prompt = ChatPromptTemplate.from_template(ARTICLE_ANALYSIS_TEMPLATE)

COUNTRY_ANALYSIS_TEMPLATE = """
# Role
You are a Senior Geopolitical Analyst and Media Strategist. Your task is to synthesize multiple article analyses from {country_name} to define that nation's "Unified Strategic Perspective" on a global event.

# Context
- Global Event: {event_title_main}
- Target Country: {country_name}
- Input Data (Aggregated Article Analyses): 
{aggregated_article_analyses}

# Instructions
Synthesize the input data to provide a country-level analysis. You must output 5 quantified metrics (average/synthesis of the articles) and additional country-specific strategic insights.

## 5 Metrics to Synthesize (0.0 to 1.0 / -1.0 to 1.0):
1. score_sentiment: Overall national mood regarding the event.
2. score_objectivity: Degree of factual reporting vs. state/media bias.
3. score_urgency: How critical this country perceives the situation.
4. score_credibility: Reliability of sources cited within this country's media.
5. score_sensationalism: Level of emotional or provocative framing in this country.

## Strategic Perspectives:
- National Interest: What is at stake for {country_name}?
- Consensus Level: Are different media outlets in {country_name} aligned or divided?
- Strategic Frame: The primary "lens" used (e.g., Economic Opportunity, Security Threat).

# Output Format (JSON ONLY)
{{
  "country_code": "{country_code}",
  "metrics": {{
    "score_sentiment": {{ "score": float, "reasoning": "string" }},
    "score_objectivity": {{ "score": float, "reasoning": "string" }},
    "score_urgency": {{ "score": float, "reasoning": "string" }},
    "score_credibility": {{ "score": float, "reasoning": "string" }},
    "score_sensationalism": {{ "score": float, "reasoning": "string" }}
  }},
  "strategic_analysis": {{
    "consensus_rate": float, (0.0: Polarized, 1.0: Complete Unanimity)
    "national_interest": "string",
    "strategic_frame": "string"
  }},
  "analysis_summary_en": "3-sentence synthesis of the national perspective in English.",
  "analysis_summary_kr": "한국인 사용자를 위한 국가별 관점 종합 요약 (3문장)."
}}
"""

country_analysis_prompt = ChatPromptTemplate.from_template(COUNTRY_ANALYSIS_TEMPLATE)