from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies.auth_dependencies import get_current_user
from app.db.database import get_db

from app.api.schemas.result_schemas import Leaderboard, UserResult
from app.api.middleware.rate_limiter import rate_limit # custom rate limiter
import json

results_router = APIRouter(prefix="/results", tags=["results"], dependencies=[Depends(get_current_user)])

@results_router.get("/{test_id}/user", response_model=UserResult)
@rate_limit(max_requests=500, window=6000)  # custom rate limiter
async def get_user_result(
    test_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db)
):
    '''
    in prod, check redis cache first - present for 7 days.
    
    redis = get_redis()
    cache_key = f"result:{test_id}:{user_id}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Cache miss - query MongoDB
    '''
    result = await db.test_results.find_one({
        "test_id": test_id,
        "user_id": user.user_id
    })
    
    if not result:
        raise HTTPException(404, "Results not published yet")
    
    result.pop("_id", None)
    
    # cache for future requests
    # redis.setex(cache_key, 604800, json.dumps(result, default=str))
    
    return UserResult(**result)


@results_router.get("/{test_id}/leaderboard", response_model=list[Leaderboard])
async def get_leaderboard(
    test_id: str,
    limit: int = 100,
    offset: int = 0,
    db=Depends(get_db)
):
    '''
    paginated leaderboard, try redis first

    redis = get_redis()
    if redis.exists(f"leaderboard_ready:{test_id}"):
        # Get total users for pagination
        total_users = redis.zcard(f"leaderboard:{test_id}")
        
        # Get this page of results
        top_users = redis.zrevrange(
            f"leaderboard:{test_id}",
            offset,
            offset + limit - 1,
            withscores=True
        )
        
        leaderboard = []
        for idx, (user_id, score) in enumerate(top_users):
            leaderboard.append({
                "rank": offset + idx + 1,
                "user_id": user_id.decode(),
                "score": int(score)
            })
        
        return {
            "leaderboard": leaderboard,
            "total_users": total_users,
            "source": "redis"
        }
    '''
    # MongoDB fallback with index
    # Get total count for pagination
    total_users = await db.test_results.count_documents({"test_id": test_id})
    
    results = await db.test_results.find(
        {"test_id": test_id}
    ).sort("rank", 1).skip(offset).limit(limit).to_list(limit)
    
    leaderboard = [
        {
            "rank": r["rank"],
            "user_id": r["user_id"],
            "score": r["total_score"],
            "percentile": r["percentile"],
            "subject_scores": r["subject_scores"]
        }
        for r in results
    ]
    
    return {
        "leaderboard": leaderboard # TODO create pydantic schema for leaderboard
    }