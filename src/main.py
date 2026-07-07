import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

from appflow.router import authentication
from appflow.router.root import root_router
from appflow.router.vehicle_report_version import version_router
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Insurance Claim API"
)
# CORS Middleware.
# httpOnly auth cookies require credentials + explicit origins ("*" is rejected
# by browsers when allow_credentials=True). Set FRONTEND_URL (comma-separated for
# multiple) in the environment; local dev ports are always allowed.
_frontend_origins = [o.strip() for o in os.getenv("FRONTEND_URL", "").split(",") if o.strip()]
_allowed_origins = list(dict.fromkeys(
    _frontend_origins + ["http://localhost:5173", "http://localhost:5174"]
))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz", include_in_schema=False)
def healthcheck():
    return {"status": "ok"}

app.include_router(root_router)
app.include_router(authentication.router)
app.include_router(version_router)

UPLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "uploads"))
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "appflow", "static"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
