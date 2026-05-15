# ruff: noqa: TC001
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ai_orchestrator.llm import AnalysisRouter
from ai_orchestrator.preprocessing import compute_message_features
from pil_contracts import (
    MessageFeatureSet,
    ProjectionCommand,
    StructuredAnalysisResult,
    WindowMessagePayload,
)


class AnalysisState(TypedDict, total=False):
    source_event_id: str
    source_window_id: str
    tg_chat_id: int
    chat_type: str
    messages: list[WindowMessagePayload]
    features: MessageFeatureSet
    canonical_context: dict[str, Any]
    task_family: str
    result: StructuredAnalysisResult
    projection_command: ProjectionCommand
    trace_id: str | None


ContextLoader = Callable[[int, list[WindowMessagePayload]], Awaitable[dict[str, Any]]]


def build_analysis_graph(
    *,
    router: AnalysisRouter,
    context_loader: ContextLoader,
) -> Any:
    async def normalize_window(state: AnalysisState) -> AnalysisState:
        messages = sorted(state["messages"], key=lambda item: (item.occurred_at, item.tg_message_id))
        deduped: list[WindowMessagePayload] = []
        seen: set[int] = set()
        for message in messages:
            if message.tg_message_id in seen:
                continue
            seen.add(message.tg_message_id)
            deduped.append(message)
        features = compute_message_features(
            deduped,
            chat_type=state.get("chat_type", "private"),
        )
        return {"messages": deduped, "features": features}

    async def load_context(state: AnalysisState) -> AnalysisState:
        context = await context_loader(state["tg_chat_id"], state["messages"])
        return {"canonical_context": context}

    def route_task_family(state: AnalysisState) -> AnalysisState:
        features = state["features"]
        if features.message_count <= 1 and not features.keyword_candidates:
            family = "summarize_window"
        elif features.attachment_count or features.reply_count or features.forwarded_count:
            family = "extract_structured"
        else:
            family = "extract_structured"
        return {"task_family": family}

    async def extract_structured(state: AnalysisState) -> AnalysisState:
        result = await router.analyze(
            source_window_id=state["source_window_id"],
            messages=state["messages"],
            features=state["features"],
            canonical_context=state["canonical_context"],
        )
        return {"result": result}

    def validate_result(state: AnalysisState) -> AnalysisState:
        result = state["result"]
        if not result.summary.strip():
            result = result.model_copy(update={"summary": "Недостаточно данных для доказательного резюме."})
        return {"result": result}

    def build_projection(state: AnalysisState) -> AnalysisState:
        command = ProjectionCommand(
            source_window_id=state["source_window_id"],
            source_event_id=state["source_event_id"],
            tg_chat_id=state["tg_chat_id"],
            messages=state["messages"],
            features=state["features"],
            result=state["result"],
            trace_id=state.get("trace_id"),
        )
        return {"projection_command": command}

    graph = StateGraph(AnalysisState)
    graph.add_node("normalize_window", normalize_window)
    graph.add_node("load_context", load_context)
    graph.add_node("route_task_family", route_task_family)
    graph.add_node("extract_structured", extract_structured)
    graph.add_node("validate_result", validate_result)
    graph.add_node("build_projection", build_projection)

    graph.add_edge(START, "normalize_window")
    graph.add_edge("normalize_window", "load_context")
    graph.add_edge("load_context", "route_task_family")
    graph.add_edge("route_task_family", "extract_structured")
    graph.add_edge("extract_structured", "validate_result")
    graph.add_edge("validate_result", "build_projection")
    graph.add_edge("build_projection", END)
    return graph.compile()
