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
    from common.config import STACK_NAME, TELEPHONY_PROVIDER, VOICE_AI_PROVIDER
    return {
        "status": "ok",
        "service": "canam-assistant",
        "stack": STACK_NAME,
        "telephony": TELEPHONY_PROVIDER,
        "voice_ai": VOICE_AI_PROVIDER,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

    