"""HTTP API: POST /ask {"question": "..."}"""
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from analyst import agent, semantic
from analyst.config import DB_PATH, load_env, model_name
from analyst.llm import ModelError, OpenAIModel

app = FastAPI(title="QuerySherpa", description="Ask a business question; get checked SQL and the answer.")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=agent.MAX_QUESTION)


@lru_cache(maxsize=1)
def get_model():
    load_env()
    return OpenAIModel(model_name())


@app.get("/health")
def health():
    return {"ok": DB_PATH.exists()}


@app.get("/metrics")
def metrics():
    return semantic.layer()["metrics"]


@app.post("/ask")
def ask(body: Question, model=Depends(get_model)):
    try:
        return agent.ask(body.question, model).to_dict()
    except ModelError as exc:
        raise HTTPException(502, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
