"""Throwaway test server: the Command Center plugin API plus the host's own audio + cron routers and chat
websocket, with NO login, bound to 127.0.0.1 only. Also serves the test page. Never deployed."""
import importlib.util, os, sys
sys.path.insert(0, "/usr/local/lib/hermes-agent")
os.environ["HERMES_HOME"] = "/root/.hermes"
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse

api_path, static_dir, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
spec = importlib.util.spec_from_file_location("cc", api_path)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)
app = FastAPI()
app.include_router(cc.router, prefix="/api/plugins/hermes-command-center")
loaded = []
for name in ("audio", "cron"):
    try:
        mod = __import__("hermes_cli.web_routers." + name, fromlist=["router"])
        app.include_router(mod.router); loaded.append(name)
    except Exception as e:
        print("host router", name, "not mounted:", type(e).__name__, str(e)[:120], flush=True)
print("host routers mounted:", loaded, flush=True)


@app.websocket("/api/ws")
async def gw(ws: WebSocket):
    from tui_gateway.ws import handle_ws
    await handle_ws(ws)


@app.get("/{name}")
def static(name: str):
    p = os.path.join(static_dir, os.path.basename(name))
    return FileResponse(p) if os.path.isfile(p) else PlainTextResponse("not found", status_code=404)


uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
