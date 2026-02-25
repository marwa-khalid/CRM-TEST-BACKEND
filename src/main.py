from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from appflow.router import authentication
from appflow.router.root import root_router

app = FastAPI(
    title="Insurance Claim API"
)
# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(root_router)
app.include_router(authentication.router)


