from celery import Celery

from app.config import settings

celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,      
    backend=settings.CELERY_RESULT_BACKEND,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        'evaluate_test_after_close': {'queue': 'evaluation'}
    }
)

'''
for chaining tasks, we would specify imports and task_routes when creating celery app
'''

# app/worker/worker.py
from celery import Celery
from app.config import settings

celery_app = Celery(
    "exam_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)