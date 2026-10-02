"""
API v1 Router

Combines all v1 endpoints into a single router.
"""

from fastapi import APIRouter

from app.api.v1 import admin, agents, browser, chat, collaboration, code, identity, input as input_router, memory, plans, plugins, status, sync, tools, voice

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(status.router, prefix="/status", tags=["status"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(plugins.router, prefix="/plugins", tags=["plugins"])
api_router.include_router(browser.router, prefix="/browser", tags=["browser"])
api_router.include_router(code.router, prefix="/code", tags=["code"])
api_router.include_router(plans.router, prefix="/plan", tags=["plan"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(input_router.router, prefix="/input", tags=["input"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(identity.router, prefix="/admin/auth", tags=["identity"])
api_router.include_router(collaboration.router, prefix="/admin", tags=["collaboration"])
