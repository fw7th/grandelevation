import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.routers import (
    admin,
    auth,
    build,
    catalog,
    checkout,
    favorites,
    products,
    search,
    shop,
)

load_dotenv()
SECRET_KEY = os.getenv("SESSION_MIDDLEWARE_SECRET_KEY")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=3600,  # optional: session cookie expiry in seconds
)

# Routers
app.include_router(admin.router)
app.include_router(products.router)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(favorites.router)
app.include_router(shop.router)
app.include_router(search.router)
app.include_router(build.router)
app.include_router(checkout.router)


@app.get("/")
async def home():
    from fastapi.responses import FileResponse

    return FileResponse("app/static/index.html")
