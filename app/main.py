from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import admin, auth, build, catalog, favorites, products, shop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(admin.router)
app.include_router(products.router)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(favorites.router)
app.include_router(shop.router)
# app.include_router(build.router)


@app.get("/")
async def home():
    from fastapi.responses import FileResponse

    return FileResponse("app/static/index.html")
