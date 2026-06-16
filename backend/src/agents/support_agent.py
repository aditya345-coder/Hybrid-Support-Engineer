import os
import re
import sqlite3
from typing import TypedDict, List

from utils.logging_config import setup_logging
from langgraph.graph import StateGraph, END

from database.hybrid_retriever import HybridRetriever
from agents.llm_gateway import LLMGateway
from settings import settings
from utils.validators import sanitize_llm_input

from langgraph.checkpoint.memory import MemorySaver

logger = setup_logging(__name__)


class AgentState(TypedDict):
    query: str
    original_query: str
    rewritten_query: str
    repo_name: str
    session_id: str
    detected_feature: str
    documents: List[str]
    code_results: List[str]
    github_issues: List[str]
    web_results: List[str]
    response: str
    is_relevant: bool
    is_hallucination: bool
    iteration: int
    allow_web_search: bool


class SupportAgent:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.llm = LLMGateway()
        self.workflow = StateGraph(AgentState)

        # Define nodes
        self.workflow.add_node("analyze", self.analyze_query)
        self.workflow.add_node("rewrite", self.rewrite_query)
        self.workflow.add_node("retrieve", self.retrieve_context)
        self.workflow.add_node("web_search", self.web_search)
        self.workflow.add_node("generate", self.generate_answer)
        self.workflow.add_node("verify", self.verify_answer)
        self.workflow.add_node("end_with_refusal", self.end_with_refusal)

        # Define flow
        self.workflow.set_entry_point("analyze")
        self.workflow.add_conditional_edges(
            "analyze", self.route_after_analyze, {"refuse": "end_with_refusal", "continue": "rewrite"}
        )
        self.workflow.add_edge("rewrite", "retrieve")
        self.workflow.add_conditional_edges(
            "retrieve",
            self.route_after_retrieve,
            {"web": "web_search", "generate": "generate"},
        )
        self.workflow.add_edge("web_search", "generate")
        self.workflow.add_edge("generate", "verify")

        # Conditional Edge (The Loop)
        self.workflow.add_conditional_edges(
            "verify", self.should_continue, {"retry": "retrieve", "end": END}
        )

        self.app = self.workflow.compile(checkpointer=self._setup_checkpointer())

        target = (settings.TARGET_REPO or "").strip()
        self.app.name = f"Support-Agent({target})" if target else "Support-Agent"

    @staticmethod
    def _setup_checkpointer():
        cp_type = settings.CHECKPOINTER.lower()

        if cp_type == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import-not-found]
                os.makedirs("data", exist_ok=True)
                conn = sqlite3.connect(
                    settings.SQLITE_PATH,
                    detect_types=sqlite3.PARSE_DECLTYPES,
                )
                checkpointer = SqliteSaver(conn)
                logger.info("Checkpointer: SQLite")
                return checkpointer
            except ImportError:
                logger.warning("SqliteSaver not available, falling back to MemorySaver")

        elif cp_type == "postgres":
            try:
                from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-not-found]
                conn_string = settings.POSTGRES_URI or ""
                if not conn_string:
                    logger.warning("POSTGRES_URI not set, falling back to MemorySaver")
                else:
                    checkpointer = PostgresSaver.from_conn_string(conn_string)
                    logger.info("Checkpointer: PostgreSQL")
                    return checkpointer
            except ImportError:
                logger.warning("PostgresSaver not available, falling back to MemorySaver")

        logger.info("Checkpointer: Memory")
        return MemorySaver()

    def analyze_query(self, state: AgentState):
        repo = state.get("repo_name") or settings.TARGET_REPO or "this repository"
        q = sanitize_llm_input(state["query"])

        # Build conversation context from previous turns
        context_str = ""
        try:
            history = list(self.app.get_state_history(
                {"configurable": {"thread_id": state.get("session_id") or "default"}},
                limit=10,
            ))
            turns = []
            for h in reversed(history):
                vals = h.values
                user_q = vals.get("original_query") or vals.get("query", "")
                bot_r = vals.get("response", "")
                if user_q and bot_r and user_q != q:
                    turns.append(f"User: {user_q}\nAssistant: {bot_r}")
            if turns:
                context_str = "\n---\n".join(turns[-3:])
        except Exception:
            logger.debug("No conversation history available")

        relevancy_prompt = (
            "You are a strict classifier for a technical support assistant. "
            f"The assistant is specialized in {repo}. "
        )
        if context_str:
            relevancy_prompt += f"Previous conversation:\n{context_str}\n\n"
        relevancy_prompt += (
            "Given the user's query, decide if it is a technical/support question that could be answered by information from the repository "
            "(code, docs, issues) and its immediate ecosystem. "
            "Return ONLY 'True' if relevant, otherwise ONLY 'False'.\n"
            f"User query: === BEGIN USER QUERY ===\n{q}\n=== END USER QUERY ==="
        )
        rel_res = self.llm.chat([{"role": "user", "content": relevancy_prompt}])
        rel_text = self.llm.get_message_text(rel_res)
        is_relevant = "true" in rel_text.lower()

        known_features: list[str] = []
        try:
            known_features = self.retriever.graph_store.get_all_feature_names(
                session_id=state.get("session_id") or None
            )
        except Exception:
            logger.debug("Could not fetch feature names from Neo4j", exc_info=True)

        feature_q = q
        if context_str:
            feature_q = f"(in context of:\n{context_str}\n) {q}"

        if known_features:
            feature_list = ", ".join(sorted(known_features))
            feature_prompt = (
                f"Identify the most relevant feature/component in {repo} for this query: === BEGIN USER QUERY ===\n{feature_q}\n=== END USER QUERY ===.\n"
                f"Known features in this repository: [{feature_list}]\n"
                "Choose the single most relevant feature name from the list above. "
                "Return ONLY the exact feature name as written in the list, or 'None' if nothing matches."
            )
        else:
            feature_prompt = (
                f"Identify the most relevant feature/component in {repo} for this query: === BEGIN USER QUERY ===\n{feature_q}\n=== END USER QUERY ===. "
                "Return only the feature name (short) or 'None'."
            )

        feat_res = self.llm.chat([{"role": "user", "content": feature_prompt}])
        detected_feature = self.llm.get_message_text(feat_res).strip()

        if known_features and detected_feature.lower() not in [f.lower() for f in known_features]:
            if detected_feature.lower() != "none":
                logger.warning(
                    "LLM returned a feature name not in the known list",
                    extra={"detected": detected_feature, "known": known_features},
                )
                matched = [f for f in known_features if f.lower() == detected_feature.lower()]
                detected_feature = matched[0] if matched else "None"
        logger.info(
            "Analyze result",
            extra={"feature": detected_feature, "is_relevant": is_relevant},
        )
        return {
            "original_query": state.get("original_query") or q,
            "detected_feature": detected_feature,
            "is_relevant": is_relevant,
            "iteration": 0,
        }

    def route_after_analyze(self, state: AgentState):
        if not state.get("is_relevant", True):
            return "refuse"
        return "continue"

    def rewrite_query(self, state: AgentState):
        """Rewrite vague queries into search-optimized technical queries."""
        q = sanitize_llm_input(state["query"])
        prompt = (
            "Rewrite the following user question into a concise, technical, search-optimized query "
            "that would work well for semantic search over documentation and GitHub issues. "
            "Keep it to one sentence. Include any concrete entities mentioned (errors, endpoints, status codes, libraries). "
            "Do not add facts that are not present. Return ONLY the rewritten query string.\n"
            f"User question: {q}"
        )
        res = self.llm.chat([{"role": "user", "content": prompt}])
        rewritten = self.llm.get_message_text(res).strip()
        # Guard against the model returning quoted strings or empty output.
        rewritten = re.sub(r"^(?:\"|')|(?:\"|')$", "", rewritten).strip() or q
        logger.info("Rewrote query", extra={"rewritten": rewritten})
        return {"rewritten_query": rewritten, "query": rewritten}

    def retrieve_context(self, state: AgentState):
        context = self.retriever.retrieve_all(
            state["query"],
            state["detected_feature"],
            state.get("session_id") or None,
        )
        raw_docs = context.get("official_docs", [])

        if len(raw_docs) >= 5:
            raw_docs = self.retriever.rerank(state["query"], raw_docs, top_k=3)
            logger.info("Reranked documents", extra={"reranked_count": len(raw_docs)})

        formatted_docs = []
        for doc in raw_docs:
            if isinstance(doc, dict):
                source = doc.get("source", "unknown")
                text = doc.get("text", "")
                formatted_docs.append(f"[Source: {source}] | Content: {text}")
            else:
                formatted_docs.append(f"[Source: unknown] | Content: {doc}")

        raw_code = context.get("code_results", [])
        formatted_code = []
        for c in raw_code:
            if isinstance(c, dict):
                formatted_code.append(
                    f"[Source: {c.get('file_path', 'unknown')}:{c.get('line_start', '?')}] "
                    f"| Symbol: {c.get('symbol_name', 'unknown')} ({c.get('symbol_type', '?')})"
                    f" | {c.get('text', '')}"
                )

        raw_issues = context.get("known_issues", [])
        formatted_issues = []
        for issue in raw_issues:
            if isinstance(issue, str) and "Issue #" in issue and ":" in issue:
                prefix, title = issue.split(":", 1)
                issue_id = prefix.replace("Issue #", "").strip()
                formatted_issues.append(
                    f"[Source: Issue #{issue_id}] | Content: {title.strip()}"
                )
            else:
                formatted_issues.append(f"[Source: Issue #unknown] | Content: {issue}")
        logger.info(
            "Retrieved context",
            extra={
                "docs_count": len(formatted_docs),
                "code_count": len(formatted_code),
                "issues_count": len(formatted_issues),
            },
        )
        return {
            "documents": formatted_docs,
            "code_results": formatted_code,
            "github_issues": formatted_issues,
            "web_results": [],
            "iteration": state.get("iteration", 0) + 1,
        }

    def route_after_retrieve(self, state: AgentState):
        allow = bool(state.get("allow_web_search"))
        has_any_context = bool(state.get("documents")) or bool(state.get("code_results")) or bool(state.get("github_issues"))
        if allow and not has_any_context:
            return "web"
        return "generate"

    def web_search(self, state: AgentState):
        """Optional web search escape hatch, gated by allow_web_search.

        Uses Tavily API if configured via TAVILY_API_KEY.
        """
        if not state.get("allow_web_search"):
            return {"web_results": []}

        api_key = settings.TAVILY_API_KEY
        if not api_key:
            logger.warning("Web search requested but TAVILY_API_KEY is not set")
            return {"web_results": []}

        try:
            import requests  # local import to avoid affecting environments that don't use web search

            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": sanitize_llm_input(state["query"]),
                    "max_results": 5,
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("Web search failed")
            return {"web_results": []}

        results = []
        for r in (data.get("results") or [])[:5]:
            url = (r.get("url") or "").strip()
            content = (r.get("content") or r.get("snippet") or "").strip()
            if not url and not content:
                continue
            results.append(f"[External Source: {url or 'unknown'}] | Content: {content}")

        logger.info("Web search results", extra={"count": len(results)})
        return {"web_results": results}

    def end_with_refusal(self, state: AgentState):
        repo = state.get("repo_name") or settings.TARGET_REPO or "this repository"
        user_q = state.get("original_query") or state.get("query")
        logger.info("query_refused", extra={
            "query": user_q,
            "detected_feature": state.get("detected_feature", ""),
            "reason": "irrelevant_query",
        })
        msg = (
            f"I am sorry, as an AI specialized in {repo}, I cannot provide information on: {user_q}."
        )
        return {"response": msg, "is_hallucination": False}

    def generate_answer(self, state: AgentState):
        docs_context = "\n".join(state["documents"])
        code_context = "\n".join(state.get("code_results") or [])
        issues_context = "\n".join(state["github_issues"])
        web_context = "\n".join(state.get("web_results") or [])
        context_str = f"DOCS:\n{docs_context}\nCODE:\n{code_context}\nISSUES:\n{issues_context}\nWEB:\n{web_context}"
        user_query = sanitize_llm_input(state['query'])
        prompt = (
            "You are a technical support assistant. For every factual claim, you must include the "
            "source tag provided in the context at the end of the sentence (e.g., [Source: docs.md]). "
            "If you do not have a source, do not state the fact. "
            "Use [Source: <filename>] for documents and [Source: Issue #<id>] for GitHub issues. "
            "If you use web results, cite them as [External Source: <url>].\n"
            f"User question: === BEGIN USER QUERY ===\n{user_query}\n=== END USER QUERY ===\n"
            f"Context:\n{context_str}\n"
            "Provide a technical answer with citations."
        )
        res = self.llm.chat([{"role": "user", "content": prompt}])
        logger.info("Generated response")
        return {"response": self.llm.get_message_text(res)}

    def verify_answer(self, state: AgentState):
        """The Critic node: checks if the answer is grounded in the provided documents."""
        docs_context = "\n".join(state["documents"])
        code_context = "\n".join(state.get("code_results") or [])
        issues_context = "\n".join(state["github_issues"])
        web_context = "\n".join(state.get("web_results") or [])
        context_str = f"DOCS:\n{docs_context}\nCODE:\n{code_context}\nISSUES:\n{issues_context}\nWEB:\n{web_context}"
        prompt = f"""
        Analyze if the following answer is grounded in the context provided.
        Answer: {state["response"]}
        Context: {context_str}
        
        Does the answer contain information NOT present in the context? 
        Return ONLY 'True' if it is a hallucination, or 'False' if it is grounded.
        """
        res = self.llm.chat([{"role": "user", "content": prompt}])
        response_text = self.llm.get_message_text(res)
        is_hallu = "true" in response_text.lower()
        logger.info("hallucination_check", extra={
            "query": state.get("query", ""),
            "detected_feature": state.get("detected_feature", ""),
            "is_hallucination": is_hallu,
            "iteration": state.get("iteration", 0),
            "docs_count": len(state.get("documents", [])),
            "issues_count": len(state.get("github_issues", [])),
        })
        return {"is_hallucination": is_hallu}

    def should_continue(self, state: AgentState):
        if state["is_hallucination"] and state["iteration"] < settings.MAX_VERIFY_RETRIES:
            return "retry"
        return "end"

    def prune_history(self, session_id: str, max_turns: int = 10) -> None:
        config = {"configurable": {"thread_id": session_id or "default"}}
        try:
            history = list(self.app.get_state_history(config, limit=max_turns * 2))
            complete = [h for h in history if h.values.get("response")]
            if len(complete) > max_turns:
                checkpointer = getattr(self.app, "checkpointer", None)
                if checkpointer and hasattr(checkpointer, "prune"):
                    checkpointer.prune([session_id or "default"], strategy="keep_latest")
                    logger.info("Pruned conversation history", extra={"session_id": session_id})
        except NotImplementedError:
            pass
        except Exception:
            logger.debug("Could not prune history", exc_info=True)

    def cleanup_session(self, session_id: str) -> None:
        self.retriever.cleanup_session(session_id)
