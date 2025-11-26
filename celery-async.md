## periodic tasks, auto triggering, chaining, grouping, standards, all async

- use celery_app.send_task("task_name", args) for async tasks, we can also use grouping/chaining
- - chaining 
    workflow = celery_app.s(task1, args1) | celery_app.s(arg2) | celery_app.s(arg3)
    workflow.apply_async()
- - grouping for parallel tasks
    g = group(task1.s(a1), task2.s(a2), task3.s(a3))
    or 
    g = group(celery_app.s(taskname, args), ...)
    result = g.apply_async()

- auto triggering, we can use chord for triggering a task (or a chain/group) after a group, or chains for synchronous triggering

- auto triggering can also be done based on celery task success or failure, or specifying new task inside another task

- periodic tasks, use beat_schedule (celery_app.conf.beat_schedule)

- standards in service-orm, worker folder, tasks folder, config there etc.