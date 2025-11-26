from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserResult(BaseModel):
    user_id: str
    test_id: str
    total_score: int
    rank: int
    percentile: float
    attempted: int
    correct: int
    subject_scores: Dict[str, int]
    subject_percentiles: Dict[str, float]
    evaluated_at: datetime
    

class Leaderboard(BaseModel):
    rank: int
    user_id: str
    score: int
    percentile: float
    subject_scores: Dict[str, int]