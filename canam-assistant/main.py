from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from common.config import PORT
import handleAudioCalls.call_routes as call_routes
import handleAudioCalls.dashboard_routes as dashboard_routes
import handleAudioCalls.websocket_routes as websocket_routes

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"

app = FastAPI(title="Canam Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(call_routes.router, tags=["Call Handling"])
app.include_router(dashboard_routes.router)
app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket Media Stream"])

if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


@app.get("/")
async def root_dashboard_redirect():
    index = DASHBOARD_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Canam Assistant API", "docs": "/docs"}


@app.get("/health")
async def health():
    from common.runtime_stack import get_active_stack, get_telephony_provider, get_voice_ai_provider
    from common.config import WEB_SERVER_URL
    from common.telephony import plivo_console_urls, public_hostname

    active = get_active_stack()
    payload = {
        "status": "ok",
        "service": "canam-assistant",
        "stack": active["stack_name"],
        "stack_id": active["stack_id"],
        "telephony": get_telephony_provider(),
        "voice_ai": get_voice_ai_provider(),
        "stack_source": active["source"],
        "web_server_url": WEB_SERVER_URL,
    }
    if get_telephony_provider() == "plivo":
        payload["plivo_setup_url"] = "/plivo/setup"
        if WEB_SERVER_URL and not WEB_SERVER_URL.startswith("http://127.0.0.1"):
            payload["plivo_console"] = plivo_console_urls()
            payload["websocket_host"] = public_hostname()
    return payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

    