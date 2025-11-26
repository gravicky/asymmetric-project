# app/api/routes/admin_routes.py
from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies.auth_dependencies import get_admin_user # not created for skeleton
from app.worker.tasks import evaluate_test_after_close
from app.db.database import get_db
from celery.result import AsyncResult

admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_admin_user)] # only works for auth + admin user
)

@admin_router.post("/tests/{test_id}/evaluate") # can be automated later, x amount of time after test or when admin confirms no changes to test
async def trigger_evaluation(
    test_id: str,
    admin=Depends(get_admin_user),
    db=Depends(get_db)
):
    
    # validate test exists and is closed
    test = await db.tests.find_one({"test_id": test_id})
    if not test:
        raise HTTPException(404, "Test not found")
    
    if test.get("evaluated"):
        return {
            "status": "already_evaluated"
        }
    
    # check if already processing
    existing_task_id = test.get("evaluation_task_id")
    if existing_task_id:
        task = AsyncResult(existing_task_id)
        if task.state in ['PENDING', 'STARTED']:
            return {
                "status": "processing",
                "task_id": existing_task_id,
                "message": "evaluation in progress"
            }
    
    # Trigger async task
    task = evaluate_test_after_close.delay(test_id)
    
    # Store task ID for tracking
    await db.tests.update_one(
        {"test_id": test_id},
        {"$set": {"evaluation_task_id": task.id}}
    )
    
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "evaluation started"
    }
