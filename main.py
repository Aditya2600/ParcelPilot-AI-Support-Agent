from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.agent import SupportAgent
from app.llm import LLMUnavailable
from app.models import ChatRequest, ChatResponse, ConfirmRequest
from app.rag import RetrievalUnavailable
from app.sources import ParcelPilotData
from app.tools import Toolbox

ROOT = Path(__file__).parent
data = ParcelPilotData(ROOT / "data")
pool = ConnectionPool(
    conninfo=data.database_url,
    open=True,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
)
tools = Toolbox(data, pool=pool)
agent = SupportAgent(data, tools)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    pool.close()


app = FastAPI(title="ParcelPilot Support Agent", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.exception_handler(LLMUnavailable)
def planner_unavailable(request: Request, exc: LLMUnavailable):
    """Fail loudly rather than falling back to guessing.

    A support agent that keeps answering after its planner dies is a liability,
    so the request is refused and the user is pointed at a human.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "The reasoning model is unavailable, so I cannot answer reliably right now. "
                           f"Please retry or contact a human agent. ({exc})"},
    )


@app.exception_handler(RetrievalUnavailable)
def retrieval_unavailable(request: Request, exc: RetrievalUnavailable):
    """Same reasoning as the planner handler: refuse rather than guess.

    Without the retrieval store there is no grounded source pack to answer from,
    and an agent that answers a policy question from the model's own memory of
    other companies' shipping terms is worse than one that says it cannot.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "The document retrieval store is unavailable, so I cannot ground an answer "
                           f"right now. Please retry or contact a human agent. ({exc})"},
    )


@app.get("/api/health")
def health():
    """Liveness/readiness probe: the app is up and can reach its retrieval store.

    Deliberately just `SELECT 1` through the pool -- it says nothing about the
    planner (Medha), which is an external dependency the app already fails loudly
    on per-request via `LLMUnavailable` rather than treating as a readiness gate.
    """
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        return JSONResponse(status_code=503, content={"status": "unavailable", "detail": str(exc)})
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return agent.answer(request.principal, request.message)


@app.post("/api/actions/confirm")
def confirm(request: ConfirmRequest):
    return tools.confirm_action(request.principal, request.confirmation_token)


@app.get("/api/proactive")
def proactive(role: str = "support_agent", user_id: str = "ops-1"):
    from app.models import Principal
    return {"snapshot": data.snapshot, "issues": agent.triage.run(Principal(user_id=user_id, role=role))}


@app.get("/api/demo-principals")
def demo_principals():
    return [
        {"label": "Northstar customer", "user_id": "northstar-user", "role": "customer", "account_id": "ACCT-001"},
        {"label": "LumenWorks customer", "user_id": "lumen-user", "role": "customer", "account_id": "ACCT-002"},
        {"label": "Support agent", "user_id": "support-1", "role": "support_agent", "account_id": None},
        {"label": "Operations manager", "user_id": "ops-1", "role": "ops_manager", "account_id": None},
    ]
