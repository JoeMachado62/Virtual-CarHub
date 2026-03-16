from fastapi import APIRouter

from app.api.v1.routers import (
    admin,
    admin_preapproval,
    auth,
    chat,
    funding,
    inventory,
    inventory_ove,
    logistics,
    matching,
    me,
    returns,
    sourcing,
    webhooks,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_preapproval.router, prefix="/admin/preapproval", tags=["admin-preapproval"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(inventory_ove.router, prefix="/inventory/ove", tags=["inventory-ove"])
api_router.include_router(matching.router, prefix="/matching", tags=["matching"])
api_router.include_router(funding.router, prefix="/funding", tags=["funding"])
api_router.include_router(sourcing.router, prefix="/sourcing", tags=["sourcing"])
api_router.include_router(logistics.router, prefix="/logistics", tags=["logistics"])
api_router.include_router(returns.router, prefix="/returns", tags=["returns"])
