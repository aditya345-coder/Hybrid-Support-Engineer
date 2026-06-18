import json
import re
from typing import Callable

from github import Github
from database.graph_store import GraphStore
from agents.llm_gateway import LLMGateway
from utils.logging_config import setup_logging
from settings import settings

logger = setup_logging(__name__)

MENTION_RE = re.compile(r"#(\d+)")
_GITHUB_URL_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?$"
)


def _parse_github_url(url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL or return as-is if already in that format."""
    m = _GITHUB_URL_RE.match(url.strip().rstrip("/"))
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return url.strip()


class GitHubGraphLoader:
    def __init__(
        self,
        repo_url: str | None = None,
        token: str | None = None,
        session_id: str | None = None,
        progress_cb: Callable[[str, int, int, str], None] | None = None,
    ):
        gh_token = token or settings.GITHUB_TOKEN
        target_repo = _parse_github_url(repo_url or settings.TARGET_REPO or "")
        if not target_repo:
            raise ValueError("repo_url or TARGET_REPO must be provided")
        self.session_id = session_id
        self.gh = Github(gh_token)
        self.repo = self.gh.get_repo(target_repo)
        self.graph_store = GraphStore()
        self.llm = LLMGateway()
        self.progress_cb = progress_cb
        logger.info(
            "GitHubGraphLoader initialized",
            extra={"repo": target_repo, "session_id": session_id or ""},
        )

    def _progress(self, phase: str, current: int, total: int, message: str) -> None:
        cb = self.progress_cb
        if cb:
            try:
                cb(phase, current, total, message)
            except Exception:
                pass

    def extract_graph_data(self, issue_body):
        """Uses LLM to identify entities and relationships from an issue."""
        prompt = f"""
        Extract a Knowledge Graph from this GitHub Issue.
        Return ONLY valid JSON with keys: 'features', 'versions', 'relationships'.
        Issue: {issue_body[:2000]}
        """
        json_content = self.llm.extract_json(prompt)
        try:
            return json.loads(json_content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response")
            return {"features": [], "versions": [], "relationships": []}

    def extract_graph_data_batch(self, issue_bodies: list[str]) -> list[dict]:
        """Uses LLM to extract graph data for multiple issues in one call.

        Returns a list of dicts, one per issue, each with keys:
        'features', 'versions', 'relationships'.
        Falls back to empty dicts for issues that fail to parse.
        """
        if not issue_bodies:
            return []

        numbered = "\n".join(
            f"Issue {i}:\n{body[:1500]}" for i, body in enumerate(issue_bodies)
        )
        prompt = f"""
        Extract a Knowledge Graph from each of the following GitHub Issues.
        Return ONLY a valid JSON array where each element corresponds to an issue
        (in the same order) with keys: 'features', 'versions', 'relationships'.

        {numbered}
        """
        json_content = self.llm.extract_json(prompt)
        try:
            results = json.loads(json_content)
            if not isinstance(results, list):
                logger.warning("Batch LLM returned non-list, falling back to per-issue")
                return [self.extract_graph_data(b) for b in issue_bodies]
            # Pad if LLM returned fewer results than input
            while len(results) < len(issue_bodies):
                results.append({"features": [], "versions": [], "relationships": []})
            return results[: len(issue_bodies)]
        except json.JSONDecodeError:
            logger.warning("Failed to parse batch LLM JSON, falling back to per-issue")
            return [self.extract_graph_data(b) for b in issue_bodies]

    @staticmethod
    def _parse_cross_references(body: str | None) -> list[str]:
        if not body:
            return []
        
        valid_mentions = []
        for mention_id in MENTION_RE.findall(body):
            if re.match(r"^\d+$", mention_id):
                valid_mentions.append(mention_id)
            else:
                logger.warning("Discarded invalid mention ID", extra={"mention_id": mention_id})
        
        return list(set(valid_mentions))

    def save_to_neo4j(self, issue_id, graph_data, author_login=None, body=None):
        mentions = self._parse_cross_references(body) if body else []
        title = graph_data.get("title", "No Title")
        features = graph_data.get("features", [])
        session_id_clause = "SET i.session_id = $session_id" if self.session_id else ""

        query = f"""
        MERGE (i:Issue {{neo4j_id: $id}})
        SET i.id = $id, i.title = $title, i.body = $body
        {session_id_clause}
        FOREACH (feat IN $features |
            MERGE (f:Feature {{name: feat}})
            MERGE (i)-[:AFFECTS]->(f)
            {"SET f.session_id = $session_id" if self.session_id else ""}
        )
        """
        if author_login:
            query += """
            MERGE (u:User {login: $author_login})
            MERGE (u)-[:OPENED]->(i)
            """
        
        if mentions:
            query += """
            UNWIND $mention_ids AS mention_id
            MERGE (other:Issue {neo4j_id: mention_id})
            MERGE (i)-[:MENTIONS]->(other)
            """

        params: dict = {
            "id": str(issue_id),
            "title": title,
            "body": body or "",
            "features": features,
            "author_login": author_login or "",
            "mention_ids": mentions,
        }
        if self.session_id:
            params["session_id"] = self.session_id

        try:
            with self.graph_store.driver.session() as session:
                session.run(query, **params)
        except Exception:
            logger.exception(
                "Failed to save issue to Neo4j",
                extra={"issue_id": issue_id},
            )

    def run(self):
        issues: list = list(self.repo.get_issues(state="closed")[:settings.MAX_ISSUES_FETCHED])
        total = len(issues)
        self._progress("building_graph", 0, max(1, total), f"Processing GitHub issues (0/{total})")

        batch_size = 10
        issue_list = list(issues)
        idx = 0

        for batch_start in range(0, len(issue_list), batch_size):
            batch = issue_list[batch_start: batch_start + batch_size]
            bodies = [issue.body or "" for issue in batch]

            batch_results = self.extract_graph_data_batch(bodies)

            for issue, data in zip(batch, batch_results):
                idx += 1
                logger.info("Processing issue", extra={"issue": issue.number})
                if isinstance(data, dict) and "title" not in data:
                    data["title"] = issue.title
                author = issue.user.login if issue.user else None
                self.save_to_neo4j(issue.number, data, author_login=author, body=issue.body)
                msg = f"Processing GitHub issues ({idx}/{total}): #{issue.number}"
                self._progress("building_graph", idx, max(1, total), msg)

        logger.info("Graph populated")


if __name__ == "__main__":
    loader = GitHubGraphLoader()
    loader.run()
