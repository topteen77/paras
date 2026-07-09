from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from common.config import PORT
import handleAudioCalls.call_routes as call_routes
import handleAudioCalls.websocket_routes as websocket_routes

app = FastAPI(title="Canam Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(call_routes.router, tags=["Call Handling"])
app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket Media Stream"])


@app.get("/health")
async def health():
    from common.config import STACK_NAME, TELEPHONY_PROVIDER, VOICE_AI_PROVIDER, WEB_SERVER_URL
    from common.telephony import plivo_console_urls, public_hostname

    payload = {
        "status": "ok",
        "service": "canam-assistant",
        "stack": STACK_NAME,
        "telephony": TELEPHONY_PROVIDER,
        "voice_ai": VOICE_AI_PROVIDER,
        "web_server_url": WEB_SERVER_URL,
    }
    if TELEPHONY_PROVIDER == "plivo":
        payload["plivo_setup_url"] = "/plivo/setup"
        if WEB_SERVER_URL and not WEB_SERVER_URL.startswith("http://127.0.0.1"):
            payload["plivo_console"] = plivo_console_urls()
            payload["websocket_host"] = public_hostname()
    return payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

    