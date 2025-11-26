# app/worker/tasks.py
from app.worker.worker import celery_app
from collections import defaultdict
from datetime import datetime
import json

from app.db.database import db 
# from app.core.redis import get_redis

@celery_app.task(name="evaluate_test_after_close", bind=True)
def evaluate_test_after_close(self, test_id: str):

    try:

        questions = list(db.questions.find({"test_id": test_id}))
        correct_answers = {q["question_id"]: q["correct_option"] for q in questions}
        
        # calculate scores for all users
        user_scores = defaultdict(lambda: {
            "total": 0,
            "subjects": defaultdict(int),
            "attempted": 0,
            "correct": 0
        })
        
        # streaming, does not load all into memory
        submissions = db.draft_submissions.find({
            "test_id": test_id,
            "final_submit": True
        })
        
        for sub in submissions:
            user_id = sub["user_id"]
            selected = sub.get("selected_option")
            correct = correct_answers.get(sub["question_id"])
            
            if selected is not None:
                user_scores[user_id]["attempted"] += 1
            
            # calculate score using the snapshot, created during start - so students know what they are attempting/risks
            if selected == correct:
                score = sub["marks_correct_snapshot"]
                user_scores[user_id]["correct"] += 1
            elif selected is None:
                score = 0
            else:
                score = sub["marks_wrong_snapshot"]
            
            user_scores[user_id]["total"] += score

            # subject also snapshotted so changing subjects is tracked
            user_scores[user_id]["subjects"][sub["subject_snapshot"]] += score
        
        # calculate ranks (in memory, fast)
        sorted_users = sorted(
            user_scores.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )
        
        total_users = len(sorted_users)
        results = []

        subject_rankings = {}
        for subject in set(s for scores in user_scores.values() for s in scores["subjects"].keys()):
            subject_scores = [
                (uid, udata["subjects"].get(subject, 0))
                for uid, udata in user_scores.items()
            ]
            subject_scores.sort(key=lambda x: x[1], reverse=True)
            subject_rankings[subject] = {uid: rank for rank, (uid, _) in enumerate(subject_scores, 1)}
            # for rank, (uid, score) in enumerate(subject_scores, 1): - if cache is used for subject ranking
            #   subject_rankings[subject][uid] = (rank, score) - if cache is used for subject ranking
        
        for rank, (user_id, scores) in enumerate(sorted_users, 1):
            percentile = ((total_users - rank) / total_users) * 100
            
            # subject-wise percentiles
            subject_percentiles = {}
            for subject in scores["subjects"]:
                subj_rank = subject_rankings[subject][user_id]
                total_in_subject = len(subject_rankings[subject])
                subj_percentile = ((total_in_subject - subj_rank) / total_in_subject) * 100
                subject_percentiles[subject] = round(subj_percentile, 2)
            
            results.append({
                "user_id": user_id,
                "test_id": test_id,
                "total_score": scores["total"],
                "rank": rank,
                "percentile": round(percentile, 2),
                "attempted": scores["attempted"],
                "correct": scores["correct"],
                "subject_scores": dict(scores["subjects"]),
                "subject_percentiles": subject_percentiles,
                "evaluated_at": datetime.utcnow()
            })
        
        if results:
            db.test_results.insert_many(results, ordered=False)

        # prod: cache results in Redis for fast reads
        # redis = get_redis()
        # pipe = redis.pipeline()
        # 
        # # Cache leaderboard
        # for r in results:
        #     pipe.zadd(f"leaderboard:{test_id}", {r["user_id"]: r["total_score"]})
        #     
        # # Subject-wise leaderboards
        # for subject, subject_scores in subject_rankings.items():
        #   for uid, (_, score) in subject_scores.items():
        #   pipe.zadd(f"leaderboard:{test_id}:{subject}", {uid: score})
        # 
        # # Cache individual results (TTL: 7 days)
        # for r in results:
        #     pipe.setex(
        #         f"result:{test_id}:{r['user_id']}", 
        #         604800,  # 7 days
        #         json.dumps(r, default=str)
        #     )
        # pipe.set(f"leaderboard_ready:{test_id}", 1)
        # pipe.execute()
        
        # Mark test as evaluated
        db.tests.update_one(
            {"test_id": test_id},
            {"$set": {"evaluated": True, "evaluated_at": datetime.utcnow()}}
        )
        
        return {
            "status": "completed",
            "test_id": test_id
        }
        
    except Exception as e:
        # log to database
        raise self.retry(exc=e, countdown=60, max_retries=3)


