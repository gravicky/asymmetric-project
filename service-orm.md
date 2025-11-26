- Seperate routes using their purpose/function - eg: auth, exam, result etc

- Use schemas folder to store all variables/schemas using pydantic, each file there being specified for a route etc

- have a services folder for APIs, with each individual file in services folder being specific to a route

api/
    routes/
        route-type1
        route-type2
    schemas/
        schema-route-type1
    services/
        service-route1
        service-route2

- db odm like beanie

- in db folder, create folders for models, migrations

db/
    main.py
    models
    migrations

- add generic names/functions in __init__ files

- seperate compute/operations in worker folder, and list task files there corresponding to their operations - like i/o tasks, result processing tasks etc

worker/
    tasks/
        task1
        task2
    worker.py
    schemas/

- pydantic schemas folder insider worker as well, for schemas used in tasks.

- central config file can be split into ones only configuring backend, db, and workers - multiple classes or multiple files.

