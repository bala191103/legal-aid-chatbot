"""
RAG Evaluation Utilities - Computes RAGAS metrics for each response.
Metrics are for evaluation only and do not affect response generation.
"""

from __future__ import annotations

from typing import Dict, List
from functools import lru_cache
import logging
import config


def _trim_contexts(contexts: List[str]) -> List[str]:
    trimmed = []
    for c in contexts[: config.METRICS_CONTEXT_TOP_K]:
        if not c:
            continue
        trimmed.append(c[: config.METRICS_CONTEXT_MAX_CHARS])
    return trimmed


@lru_cache(maxsize=1)
def _get_eval_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(
        api_key=config.GROQ_METRICS_API_KEY,
        model_name=config.METRICS_LLM_MODEL,
        temperature=0.0,
        max_tokens=config.METRICS_LLM_MAX_TOKENS,
        n=1,
    )


@lru_cache(maxsize=1)
def _get_embeddings():
    from langchain_community.embeddings import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)


def evaluate_rag_metrics(question: str, answer: str, contexts: List[str]) -> Dict:
    """
    Compute RAG-based metrics using RAGAS if available.
    Returns dict with metric values in [0, 1] or None if unavailable.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import context_precision, context_recall, faithfulness
        try:
            from ragas.metrics import answer_relevancy
        except Exception:
            from ragas.metrics import answer_relevance as answer_relevancy
        from datasets import Dataset
    except Exception as e:
        return {
            "error": f"RAGAS not available: {str(e)}",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }

    contexts = _trim_contexts(contexts)
    if not contexts:
        return {
            "status": "skipped",
            "reason": "Not applicable – no retrieved context",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }
    if not answer or not answer.strip():
        return {
            "status": "skipped",
            "reason": "Not applicable – empty answer",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }
    answer = answer[: config.METRICS_ANSWER_MAX_CHARS]

    # Proxy ground truth: use the top retrieved chunk as a reference.
    # This avoids LLM-as-judge references while keeping RAGAS inputs valid.
    data = {
        "question": [question],
        "answer": [answer],
        "contexts": [contexts],
        "ground_truths": [[contexts[0]]],
        "reference": [contexts[0]],
    }

    dataset = Dataset.from_dict(data)
    try:
        if not config.GROQ_METRICS_API_KEY:
            return {
                "error": "Groq metrics API key missing. Set GROQ_METRICS_API_KEY to compute RAGAS metrics.",
                "context_precision": None,
                "context_recall": None,
                "faithfulness": None,
                "answer_relevancy": None,
            }
        llm = _get_eval_llm()
        embeddings = _get_embeddings()
    except Exception as exc:
        logging.error("Metrics init failed: %s", exc)
        llm = None
        embeddings = None

    if llm is None or embeddings is None:
        return {
            "error": "Metrics LLM or embeddings unavailable. Check configuration, model name, and dependencies.",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }

    try:
        result = evaluate(
            dataset,
            metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
            llm=llm,
            embeddings=embeddings,
        )
        def _to_float(value):
            if isinstance(value, list) and value:
                value = value[0]
            try:
                return float(value)
            except Exception:
                return float("nan")

        metrics = {
            "status": "computed",
            "context_precision": _to_float(result["context_precision"]),
            "context_recall": _to_float(result["context_recall"]),
            "faithfulness": _to_float(result["faithfulness"]),
            "answer_relevancy": _to_float(result["answer_relevancy"]),
        }
        if any(str(metrics[k]) == "nan" for k in ("context_precision", "context_recall", "faithfulness", "answer_relevancy")):
            metrics["status"] = "computed_with_na"
            metrics["reason"] = "One or more metrics returned NA from RAGAS. This can happen when RAGAS cannot align answer statements to context."
            for k in ("context_precision", "context_recall", "faithfulness", "answer_relevancy"):
                if str(metrics[k]) == "nan":
                    metrics[k] = None
        return metrics
    except Exception as e:
        if "LLMDidNotFinishException" in str(e):
            return {
                "error": "RAGAS LLM did not finish. Increase METRICS_LLM_MAX_TOKENS.",
                "context_precision": None,
                "context_recall": None,
                "faithfulness": None,
                "answer_relevancy": None,
            }
        # Best-effort extraction of HTTP error body (e.g., Groq 400)
        try:
            response = getattr(e, "response", None)
            if response is not None:
                try:
                    logging.error("RAGAS HTTP error response: %s", response.text)
                except Exception:
                    logging.error("RAGAS HTTP error response (repr): %r", response)
        except Exception:
            pass
        return {
            "error": f"RAGAS evaluation failed: {str(e)}",
            "context_precision": None,
            "context_recall": None,
            "faithfulness": None,
            "answer_relevancy": None,
        }
