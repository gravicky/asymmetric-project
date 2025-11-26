from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies.auth_dependencies import get_current_user
from app.db.database import get_db
from typing import Optional

# import json
import bisect

predictions_router = APIRouter(prefix="/predictions", tags=["predictions"])


@predictions_router.post("/predict-rank")
async def predict_rank(
    mock_test_id: str,
    user=Depends(get_current_user),
    db=Depends(get_db),
    reference_test_id: str = "CAT2024"  # real exam to compare against
):
    '''
    predict rank/percentile for mock test based on real exam distribution
    
    approach
    1. get mock test scores
    2. load reference distribution (CAT 2024 here)
    3. find where user's score ranks in that distribution
    4. return predicted rank/percentile
    
    - accuracy: high if mock difficulty similar to real difficulty
    - speed: O(log N) binary search vs O(N) linear
    '''
    
    # Step 1: Get user's mock test result
    '''
    in prod, check redis cache first - present for 7 days.
    
    redis = get_redis()
    cache_key = f"result:{test_id}:{user_id}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Cache miss - query MongoDB
    '''
    mock_result = await db.test_results.find_one({
        "test_id": mock_test_id,
        "user_id": user.user_id
    })
    
    if not mock_result:
        raise HTTPException(404, "Mock test not submitted yet")
    
    # in prod, cache this as well - on startup, below, ttl 30 days after mock
    reference_results = await db.test_results.find(
        {"test_id": reference_test_id}
    ).to_list(None)
    
    if not reference_results:
        raise HTTPException(404, f"Reference test {reference_test_id} not found")
    
    predicted_rank = predict_rank_internal(
        mock_result["total_score"],
        reference_results,
        "total_score"
    )
    
    total_users = len(reference_results)
    predicted_percentile = ((total_users - predicted_rank) / total_users) * 100
    
    subject_predictions = {}
    for subject, mock_score in mock_result["subject_scores"].items():
        subject_rank = predict_rank_internal(
            mock_score,
            reference_results,
            "subject_scores",
            subject
        )
        
        # count num users in reference who wrote thi subject
        subject_count = sum(
            1 for r in reference_results 
            if subject in r.get("subject_scores", {})
        )
        
        subject_percentile = ((subject_count - subject_rank) / subject_count) * 100
        subject_predictions[subject] = {
            "predicted_rank": subject_rank,
            "predicted_percentile": round(subject_percentile, 2)
        }
    
    return {
        "mock_test_id": mock_test_id,
        "reference_test": reference_test_id,
        "user_score": mock_result["total_score"],
        "predicted_rank": predicted_rank,
        "predicted_percentile": round(predicted_percentile, 2),
        "subject_predictions": subject_predictions
    }


def predict_rank_internal(user_score: int, reference_results: list, 
                          score_field: str, subject: Optional[str] = None) -> int:
    
    if score_field == "total_score":
        scores = sorted(
            [r["total_score"] for r in reference_results],
            reverse=True
        )
    else:  # subject_scores
        scores = sorted(
            [r["subject_scores"].get(subject, 0) for r in reference_results],
            reverse=True
        )
    
    # binary search
    rank = bisect.bisect_left([-s for s in scores], -user_score) + 1
    
    return rank


 


# in prod, cache reference distributions to avoid reloading
# this will be present and run from lifespan in main.py in prod code
async def load_reference_distributions():
    '''
    pre load and cache historical distributions
    call once on startup, update daily
    
    redis = get_redis()
    
    # Load CAT 2024 distribution
    cat2024_results = await db.test_results.find(
        {"test_id": "CAT2024"}
    ).to_list(None)
    
    # Store sorted score lists in Redis (compressed)
    overall_scores = sorted(
        [r["total_score"] for r in cat2024_results],
        reverse=True
    )
    
    redis.set(
        "distribution:CAT2024:overall",
        json.dumps(overall_scores),
        ex=2592000  # 30 days
    )
    
    similarly, store subject scores in redis as well

    compute scores
    redis.set(
            f"distribution:CAT2024:{subject}",
            json.dumps(subject_scores),
            ex=2592000
        )
    '''    