from pymongo import AsyncMongoClient
from pymongo import ASCENDING, DESCENDING
from app.config import settings

client = AsyncMongoClient(settings.DATABASE_URL)
db = client.exam_platform

# create indexes once at startup
async def init_indexes():
    # users
    # index 1, for auth
    await db.users.create_index("user_id", unique=True)
    
    # questions
    # index 1, read all questions for specific test
    await db.questions.create_index([("test_id", ASCENDING)])
    
    # draft submissions
    # index 1, for start_exam, check if already started
    await db.draft_submissions.create_index(
        [("user_id", ASCENDING), ("test_id", ASCENDING)],
        name="user_test_lookup"
    )

    # index 2, for save_draft_answer, update single answer
    await db.draft_submissions.create_index(
        [("user_id", ASCENDING), ("test_id", ASCENDING), ("question_id", ASCENDING)],
        unique=True,
        name="unique_user_answer"
    )

    # index 3, for evaluation, read all submitted answers
    await db.draft_submissions.create_index(
        [("test_id", ASCENDING), ("final_submit", ASCENDING)],
        name="eval_query_index"
    )

    # test results
    # index 1, for get_user_result, ie single user result
    await db.test_results.create_index(
        [("test_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="user_result_lookup"
    )
    
    # index 2, get_leaderboard, sorted by rank
    # Query: {"test_id": X} SORT BY rank
    await db.test_results.create_index(
        [("test_id", ASCENDING), ("rank", ASCENDING)],
        name="leaderboard_lookup"
    )

# from our latest projects we are using pymongo instead of motor, since pymongo now has native async support, and motor is depreciated

# migration tools can be added here if required