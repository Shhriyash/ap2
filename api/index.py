"""Vercel serverless entry point — re-exports the FastAPI app."""
import sys
from pathlib import Path

# Make gateway_service importable as `app.*`
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "gateway_service"))

# Make local shared_lib importable without editable installs on Vercel.
sys.path.insert(0, str(repo_root / "shared_lib"))

from app.main import app  # noqa: E402, F401
