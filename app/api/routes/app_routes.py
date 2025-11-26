from fastapi import APIRouter, Depends
from pymongo import AsyncMongoClient
from datetime import datetime
from uuid import uuid4

from app.api.schemas.app_schemas import SaveDraftRequest
from app.api.dependencies.auth_dependencies import get_current_user
from app.db.database import get_db
from app.config import settings

from app.api.main import limiter # slowapi rate limiter

from app.api.middleware.rate_limiter import rate_limit # custom rate limiter
from app.worker.tasks import process_data_task


app_router = APIRouter(
    prefix=settings.APP_PREFIX,
    tags=["app"],
    dependencies=[Depends(get_current_user)]  # all routes need auth
)

# exam start endpoint
@app_router.post("/exam/{test_id}/start")
async def start_exam(
    test_id: str,
    user = Depends(get_current_user),
    db = Depends(get_db)
):

    # redis = get_redis()
    # already_started = redis.exists(f"exam_started:{test_id}:{user.user_id}")
    # if already_started:
    #     return {"status": "already_started"}

    # in prod, do above
    exists = await db.draft_submissions.find_one(
        {"user_id": user.user_id, "test_id": test_id},
        projection={"_id": 1}
    )
    if exists:
        return {"status": "already_started"}
    
    questions = await db.questions.find({"test_id": test_id}).to_list(None)
    
    # index already created in database.py for draft_submission collection
    drafts = [{
        "user_id": user_id,
        "test_id": test_id,
        "question_id": q["question_id"],
        "selected_option": None,
        "time_spent_seconds": 0,
        "marked_for_review": False,
        "visited": False,
        "marks_correct_snapshot": q["marks_correct"],
        "marks_wrong_snapshot": q["marks_wrong"],
        "subject_snapshot": q["subject"],
        "final_submit": False
    } for q in questions]
    
    # indexes already exist, so this is fast
    try:
        result = await db.draft_submissions.insert_many(
            drafts, 
            ordered=False
        )

        # in prod, cache exam started
        # redis.setex(f"exam_started:{test_id}:{user.user_id}", 10800, "1")

        return {
            "status": "exam_started"
        }
        
    except Exception:
        await db.draft_submissions.delete_many({
            "user_id": user.user_id,
            "test_id": test_id
        })
        raise HTTPException(500, f"Failed to initialize exam")



@app_router.post("/exam/{test_id}/save")
@rate_limit(max_requests=500, window=6000)  # custom rate limiter
async def save_draft_answer(
    test_id: str,
    payload: SaveDraftRequest,
    user = Depends(get_current_user),
    db = Depends(get_db)
):
    await db.draft_submissions.update_one(
        {
            "user_id": user.user_id,
            "test_id": test_id,
            "question_id": payload.question_id
        },
        {"$set": {
            "selected_option": payload.selected_option,
            "marked_for_review": payload.marked_for_review,
            "visited": True,
            "time_spent_seconds": payload.time_spent_seconds,

        }},
        upsert=True
    )
    return {"status": "saved"}


@app_router.post("/exam/{test_id}/submit")
async def final_submit(
    test_id: str, 
    user=Depends(get_current_user), 
    db=Depends(get_db)
):
    # just mark as submitted
    result = await db.draft_submissions.update_many(
        {
            "user_id": user.user_id,
            "test_id": test_id,
            "final_submit": False # prevent double submit
        },
        {
            "$set": {
                "final_submit": True
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(400, "Already submitted or no answers found")
    
    return {
        "status": "submitted"
    }
