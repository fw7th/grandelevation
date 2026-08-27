import sys
from pathlib import Path

# Add project root to Python path so `app` imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
