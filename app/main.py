from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from models.user_models import create_db

app = FastAPI(title="Solar Ordering Site")


@app.on_event("startup")
def startup():
    create_db()


# Static files (CSS, htmx.js) served from app/static at /static/*
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 looks for .html files in app/templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"title": "Solar Site"},
    )


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
