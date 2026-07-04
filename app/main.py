from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    yield


app = FastAPI(lifespan=lifespan)


# Static files (CSS, htmx.js) served from app/static at /static/*
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 looks for .html files in app/templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home():
    return FileResponse("app/static/index.html")


@app.get("/signin")
async def signin():
    return FileResponse("app/static/signin.html")


@app.get("/signup")
async def signup():
    return FileResponse("app/static/signup.html")


@app.post("/api/ping", response_class=HTMLResponse)
def ping(request: Request):
    """
    A tiny htmx demo endpoint: returns a fragment of HTML, not a full page.
    This is the core pattern we'll reuse for the real compatibility checker:
    htmx sends a request, FastAPI returns a small chunk of rendered HTML,
    htmx swaps it into the page. No JSON, no client-side JS framework.
    """
    return templates.TemplateResponse(
        request=request,
        name="_ping_result.html",
        context={},
    )
