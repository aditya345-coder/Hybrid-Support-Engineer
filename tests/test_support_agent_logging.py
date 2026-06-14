import logging
from unittest.mock import patch, MagicMock


def test_verify_answer_logs_hallucination_check(caplog):
    caplog.set_level(logging.INFO)

    with (
        patch("agents.support_agent.HybridRetriever"),
        patch("agents.support_agent.LLMGateway") as mock_llm_gateway,
    ):
        mock_llm = MagicMock()
        mock_llm.chat.return_value = {"role": "assistant", "content": "True"}
        mock_llm.get_message_text.return_value = "True"
        mock_llm_gateway.return_value = mock_llm

        from agents.support_agent import SupportAgent

        agent = SupportAgent()
        agent.llm = mock_llm

        state = {
            "query": "How do I configure CORS?",
            "original_query": "How do I configure CORS?",
            "detected_feature": "middleware",
            "documents": ["[Source: docs.md] | Content: Use CORSMiddleware"],
            "github_issues": ["[Source: Issue #123] | Content: CORS bug"],
            "web_results": [],
            "response": "Use CORSMiddleware [Source: docs.md]",
            "is_relevant": True,
            "is_hallucination": False,
            "iteration": 1,
            "session_id": "test-session",
            "repo_name": "test/repo",
            "rewritten_query": "CORS configuration",
            "allow_web_search": False,
        }

        agent.verify_answer(state)

    records = [
        r for r in caplog.records
        if r.name == "agents.support_agent" and r.message.startswith("hallucination_check")
    ]
    assert len(records) >= 1
    record = records[0]
    assert record.query == "How do I configure CORS?"
    assert record.detected_feature == "middleware"
    assert record.is_hallucination is True
    assert record.iteration == 1
    assert record.docs_count == 1
    assert record.issues_count == 1


def test_end_with_refusal_logs_query_refused(caplog):
    caplog.set_level(logging.INFO)

    with (
        patch("agents.support_agent.HybridRetriever"),
        patch("agents.support_agent.LLMGateway"),
    ):
        from agents.support_agent import SupportAgent

        agent = SupportAgent()

        state = {
            "query": "What is the weather?",
            "original_query": "What is the weather?",
            "detected_feature": "",
            "documents": [],
            "github_issues": [],
            "web_results": [],
            "response": "",
            "is_relevant": False,
            "is_hallucination": False,
            "iteration": 0,
            "session_id": "",
            "repo_name": "test/repo",
            "rewritten_query": "",
            "allow_web_search": False,
        }

        agent.end_with_refusal(state)

    records = [
        r for r in caplog.records
        if r.name == "agents.support_agent" and r.message.startswith("query_refused")
    ]
    assert len(records) >= 1
    record = records[0]
    assert record.query == "What is the weather?"
    assert record.detected_feature == ""
    assert record.reason == "irrelevant_query"
