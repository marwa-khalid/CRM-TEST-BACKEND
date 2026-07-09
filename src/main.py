import os

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

from appflow.router import authentication
from appflow.router.root import root_router
from appflow.router.vehicle_report_version import version_router
from appflow.router.fleet import fleet_router
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Insurance Claim API"
)
# CORS Middleware.
# httpOnly auth cookies require credentials + explicit origins ("*" is rejected
# by browsers when allow_credentials=True). Set FRONTEND_URL, FRONTEND_BASE_URL,
# or CORS_ALLOWED_ORIGINS (comma-separated) in the environment.
def _split_origins(*values: str):
    origins = []
    for value in values:
        origins.extend(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())
    return origins


_allowed_origins = list(dict.fromkeys(
    _split_origins(
        os.getenv("CORS_ALLOWED_ORIGINS", ""),
        os.getenv("FRONTEND_URL", ""),
        os.getenv("FRONTEND_BASE_URL", ""),
    )
    # Local dev ports + the production Netlify origin are always allowed, so CORS
    # works out of the box even without a host env var. FRONTEND_URL still drives
    # email links (witness_email.py); set it per environment:
    #   local -> http://localhost:5174 ; prod -> https://claims-crm.netlify.app
    + [
        "http://localhost:5173",
        "http://localhost:5174",
        "https://claims-crm.netlify.app",
        "http://claims-crm.netlify.app",
    ]
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
app.include_router(fleet_router)

UPLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "uploads"))
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "appflow", "static"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
