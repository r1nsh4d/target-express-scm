from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    advances,
    auth,
    billing,
    consignments,
    dashboard,
    driver,
    expenses,
    freights,
    masters,
    masters_edit,
    presets,
    public,
    tracking,
    uploads,
)
from app.core.config import settings

app = FastAPI(
    title="Target Express API",
    description="Delivery management platform for Target Express Logistics",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(driver.router)
app.include_router(advances.router)
app.include_router(masters.router)
app.include_router(masters_edit.router)
app.include_router(presets.router)
# Registered after masters so /api/freights/{id}/account from advances keeps
# working alongside the freight lifecycle routes.
app.include_router(freights.router)
app.include_router(consignments.router)
app.include_router(billing.router)
app.include_router(expenses.router)
app.include_router(uploads.router)
app.include_router(public.admin_router)
# Public and unauthenticated. tracking: the token in the link is the
# credential. public: rate limited, and a lookup needs a second factor.
app.include_router(tracking.router)
app.include_router(public.router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
