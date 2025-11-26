# rbac

- admin, editor and viewer

- editor - create, read, update, not read

- viewer

- seperate the routes for admin, editor, viewer, and in APIRoutes, add a dependency for checking login status, and role of user

- if roles are very similar, each route can have its own dependency for checking role

    eg: if APIRouter/request has a requirement for 'delete' to be allowed to use the route, we get the output of dependency and only allow api to be accessed if its True

- dependency - gets username from HTTPBearer, checks db for role and sends True/False based on whether they have that ability

async def get_current_user_role(credentials = Depends(security)) -> dict:
    try:
        payload = decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=settings.ALGORITHM
        )
        db = await db.users.find_one({"user_id": payload.id})
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")