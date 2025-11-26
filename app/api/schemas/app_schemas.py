from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class SaveDraftRequest(BaseModel):
    question_id: str
    selected_option: Optional[int] = None
    marked_for_review: bool = False
    time_spent_seconds: int