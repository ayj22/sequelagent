"""HTTP API: POST /ask {"question": "..."}"""
import hmac
import os
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from analyst import agent, semantic
from analyst.config import DB_PATH, load_env, model_name
from analyst.limits import RateLimit
from analyst.llm import ModelError, OpenAIModel

app = FastAPI(title="SequelAgent: Governed AI Analyst Agent for Footwear Retail and Wholesale",
              description="Ask a business question in plain English; get checked, read-only SQL and the answer.")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=agent.MAX_QUESTION)


@lru_cache(maxsize=1)
def get_model():
    load_env()
    return OpenAIModel(model_name())


limiter = RateLimit(calls=30, seconds=60)


def guard(authorization: str = Header(default="")) -> None:
    """Optional shared token (set SEQUELAGENT_API_TOKEN) and a limit on how often the model can be called."""
    token = os.environ.get("SEQUELAGENT_API_TOKEN", "")
    if token and not hmac.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Missing or wrong token")
    if not limiter.allow():
        raise HTTPException(429, "Too many questions: wait a minute")


@app.get("/health")
def health():
    return {"ok": DB_PATH.exists()}


@app.get("/metrics")
def metrics():
    return semantic.layer()["metrics"]


@app.post("/ask", dependencies=[Depends(guard)])
def ask(body: Question, model=Depends(get_model)):
    try:
        return agent.ask(body.question, model).to_dict()
    except ModelError as exc:
        raise HTTPException(502, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
