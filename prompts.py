from langchain_core.prompts import ChatPromptTemplate

ARTICLE_ANALYSIS_TEMPLATE = """
# Role
You are an adversarial Media Analyst. You are trained to detect hidden agenda, geopolitical bias, and logical fallacies in international news reports.

# Context
- Event Summary: {event_title_main} ({event_summary_main})
- Article Title: {article_title}
- Article URL: {article_url}
- Article Body: {article_body}


Mandatory Logic: If the URL domain belongs to a state-controlled entity, heavily penalize the 'Credibility' and 'Objectivity' scores unless the content is purely administrative.
# Instructions
1. Analyze the article in the context of the global event.
2. Crucially, evaluate the article based on its 'Source Context'. Consider the credibility, potential political bias, and national stance typically associated with the domain found in the URL.
3. For each metric, provide a score (float) and a brief reasoning (max 2 sentences in English).


## Scoring Rubric (Must follow for consistent analysis):


1. **Sentiment (-1.0 ~ 1.0)**
   - Score -1.0: Aggressive conflict, casualties, total diplomatic breakdown.
   - Score 0.0: Purely informational, balanced quotes from both sides.
   - Score 1.0: Peaceful resolution, cooperation, positive expectation.


2. **Objectivity (0.0 ~ 1.0)**
   - Score 1.0: Contains no adjectives, purely descriptive, cites multiple perspectives.
   - Score 0.5: Mix of facts and narrative framing.
   - Score 0.0: Loaded language, emotional appeal, or cherry-picking facts.


3. **Urgency (0.0 ~ 1.0)**
   - Score 1.0: "Just in", "Urgent", "Happening now", "Demands immediate action".
   - Score 0.5: Developments occurring over the last 24-48 hours.
   - Score 0.0: Providing historical background or concluding analysis.


4. **Credibility (0.0 ~ 1.0)**
   - Score 1.0: Verified primary sources, peer-reviewed, or major international news bureaus.
   - Score 0.5: Mainstream media but with clear editorial bias.
   - Score 0.0: State-owned propaganda, unverified social media, or anonymous blogs.


5. **Sensationalism (0.0 ~ 1.0)**
   - Score 1.0: Exaggerated headlines, inflammatory imagery, calls for public outrage.
   - Score 0.5: Moderate engagement-bait, emotive adjectives used in moderation.
   - Score 0.0: Professional, dry, academic, or formal tone.

# Source Context Analysis (Crucial Step)
- Before scoring, briefly identify the nature of the URL domain (e.g., State-owned, Public, Independent, or Corporate media).
- Factor this identity into your 'Credibility' and 'Objectivity' scores.
- Do not assign a Credibility score of 0 to government-affiliated news outlets. Instead, cap their Credibility at 0.4 to reflect their role as official state mouthpieces while distinguishing them from purely unverified or malicious fake news sources.


# Fairness & Neutrality Guidelines
Avoid assuming malice or propaganda by default.
Acknowledge that all media outlets, including public broadcasters, operate under specific national or editorial frameworks.
Your role is to identify the 'perspective', not to label the article as 'good' or 'bad'. Focus on the 'who, what, and how' of the framing rather than moral judgment.




# Output Format (JSON ONLY)
Return the analysis strictly in raw JSON format. No markdown blocks, no wrappers.
Start with {{ and end with }}.


{{
 "source_identity": "Brief description of the media outlet based on URL domain",
 "score_sentiment": {{ "score": float, "reasoning": "string" }},
 "score_objectivity": {{ "score": float, "reasoning": "string" }},
 "score_urgency": {{ "score": float, "reasoning": "string" }},
 "score_credibility": {{ "score": float, "reasoning": "string" }},
 "score_sensationalism": {{ "score": float, "reasoning": "string" }},
 "analysis_summary_en": "3-sentence summary of the core perspective, considering the outlet's typical stance.",
 "analysis_summary_kr": "위 내용을 바탕으로 한 3문장 요약 (한국어)."
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
- National Interest: What is at stake for {country_name}? (Concise, 1 sentence)
- Consensus Level: Are different media outlets in {country_name} aligned or divided?
- Strategic Frame: The primary "lens" used. MUST BE A CONCISE PHRASE (e.g., "Geopolitical Stability", "Human Rights Crisis", "Economic Sovereignty", "Security Threat"). DO NOT USE FULL SENTENCES.

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