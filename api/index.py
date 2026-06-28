"""
Vercel looks for a variable named `app` at this entrypoint (api/index.py).
We don't put real logic here — we just import the actual FastAPI app
from app/main.py, so the app code stays portable if we ever change hosts.
"""

from app.main import app  # noqa: F401
