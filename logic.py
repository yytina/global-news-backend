# logic.py
def calculate_weighted_index(articles):
    """
    상위 5개 기사의 Credibility와 Objectivity를 가중치로 하여 
    국가별 평균 인덱스를 계산합니다.
    """
    if not articles:
        return None
        
    total_weight = 0
    weighted_scores = {
        "sentiment": 0, "objectivity": 0, "urgency": 0, 
        "credibility": 0, "sensationalism": 0
    }
    
    for a in articles:
        # 가중치 결정: 신뢰도 * 객관성 (혜진 님의 핵심 로직)
        weight = (a.score_credibility or 0.5) * (a.score_objectivity or 0.5)
        
        weighted_scores["sentiment"] += (a.score_sentiment or 0) * weight
        weighted_scores["objectivity"] += (a.score_objectivity or 0) * weight
        weighted_scores["urgency"] += (a.score_urgency or 0) * weight
        weighted_scores["credibility"] += (a.score_credibility or 0) * weight
        weighted_scores["sensationalism"] += (a.score_sensationalism or 0) * weight
        
        total_weight += weight
    
    if total_weight == 0: return None
    
    # 가중 평균값 산출
    return {k: v / total_weight for k, v in weighted_scores.items()}