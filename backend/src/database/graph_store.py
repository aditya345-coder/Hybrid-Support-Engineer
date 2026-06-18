from typing import Any, cast

from neo4j import GraphDatabase

from utils.logging_config import setup_logging
from settings import settings

logger = setup_logging(__name__)


class GraphStore:
    def __init__(self):
        uri = settings.NEO4J_URI
        username = settings.NEO4J_USERNAME
        password = settings.NEO4J_PASSWORD
        if not uri or not username or not password:
            logger.error("Missing Neo4j configuration")
            raise ValueError("NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD must be set")
        uri = cast(str, uri)
        username = cast(str, username)
        password = cast(str, password)
        self.driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
        )
        logger.info("Neo4j driver initialized", extra={"uri": uri})

    def close(self):
        self.driver.close()

    def get_related_issues(
        self,
        neo4j_id: str,
        limit: int = 5,
        session_id: str | None = None,
    ):
        session_clause = ""
        if session_id:
            session_clause = " AND f.session_id = $session_id AND i.session_id = $session_id"

        query = f"""
        MATCH (f:Feature)
        WHERE (f.neo4j_id = $neo4j_id OR f.name = $neo4j_id)
        MATCH (f)<-[:AFFECTS]-(i:Issue)
        WHERE true{session_clause}
        RETURN coalesce(i.id, i.neo4j_id) AS issue_id, i.title AS title LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                params: dict[str, Any] = {"neo4j_id": neo4j_id, "limit": limit}
                if session_id:
                    params["session_id"] = session_id
                result = session.run(query, **params)
                return [f"Issue #{record['issue_id']}: {record['title']}" for record in result]
        except Exception as e:
            logger.error(f"Neo4j connection error: {e}")
            try:
                self.driver.verify_connectivity()
            except Exception:
                logger.warning("Neo4j connection lost. Attempting to reconnect...")
            return []

    def get_contributors_for_feature(
        self,
        feature_name: str,
        limit: int = 5,
        session_id: str | None = None,
    ) -> list[str]:
        session_clause = ""
        if session_id:
            session_clause = " AND f.session_id = $session_id AND i.session_id = $session_id"
        query = f"""
        MATCH (f:Feature)
        WHERE f.name = $feature_name
        MATCH (f)<-[:AFFECTS]-(i:Issue)<-[:OPENED]-(u:User)
        WHERE true{session_clause}
        RETURN u.login AS login, count(*) AS fixes
        ORDER BY fixes DESC LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                params: dict[str, Any] = {"feature_name": feature_name, "limit": limit}
                if session_id:
                    params["session_id"] = session_id
                result = session.run(query, **params)
                return [f"{record['login']} ({record['fixes']} fixes)" for record in result]
        except Exception as e:
            logger.error(f"Neo4j get_contributors_for_feature error: {e}")
            return []

    def get_files_changed_for_issue(
        self,
        issue_number: int,
        session_id: str | None = None,
    ) -> list[str]:
        session_clause = ""
        if session_id:
            session_clause = " AND i.session_id = $session_id"
        query = f"""
        MATCH (i:Issue)
        WHERE i.neo4j_id = $issue_number{session_clause}
        OPTIONAL MATCH (i)-[:FIXED_BY]->(:PR)-[:MODIFIED]->(f:File)
        RETURN COLLECT(DISTINCT f.path) AS paths
        """
        try:
            with self.driver.session() as session:
                params: dict = {"issue_number": str(issue_number)}
                if session_id:
                    params["session_id"] = session_id
                result = session.run(query, **params)
                record = result.single()
                if record and record["paths"]:
                    return list(record["paths"])
                return []
        except Exception as e:
            logger.error(f"Neo4j get_files_changed_for_issue error: {e}")
            return []

    def get_related_issues_by_text(
        self,
        keyword: str,
        limit: int = 5,
        session_id: str | None = None,
    ) -> list[str]:
        session_clause = ""
        if session_id:
            session_clause = " AND i.session_id = $session_id"
        query = f"""
        MATCH (i:Issue)
        WHERE (i.title CONTAINS $keyword OR i.body CONTAINS $keyword)
        {session_clause}
        RETURN i.neo4j_id AS number, i.title AS title
        LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                params: dict[str, Any] = {"keyword": keyword, "limit": limit}
                if session_id:
                    params["session_id"] = session_id
                result = session.run(query, **params)
                return [f"#{record['number']}: {record['title']}" for record in result]
        except Exception as e:
            logger.error(f"Neo4j get_related_issues_by_text error: {e}")
            return []

    def upsert_issue(self, issue_data: dict, session_id: str | None = None) -> None:
        """Create or update an Issue node from a webhook payload."""
        query = """
        MERGE (i:Issue {neo4j_id: $number})
        SET i.title = $title,
            i.body = $body,
            i.state = $state,
            i.url = $url,
            i.created_at = $created_at,
            i.updated_at = $updated_at,
            i.session_id = $session_id
        WITH i
        MERGE (u:User {login: $user_login})
        MERGE (u)-[:OPENED]->(i)
        """
        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    number=str(issue_data.get("number", "")),
                    title=issue_data.get("title", ""),
                    body=(issue_data.get("body") or "")[:5000],
                    state=issue_data.get("state", "open"),
                    url=issue_data.get("html_url", ""),
                    created_at=str(issue_data.get("created_at", "")),
                    updated_at=str(issue_data.get("updated_at", "")),
                    user_login=issue_data.get("user", {}).get("login", "unknown"),
                    session_id=session_id,
                )
            logger.info(
                "Issue upserted",
                extra={"issue": issue_data.get("number"), "state": issue_data.get("state")},
            )
        except Exception:
            logger.exception("Neo4j upsert_issue failed", extra={"issue": issue_data.get("number")})

    def upsert_pr(self, pr_data: dict, session_id: str | None = None) -> None:
        """Create or update a PR node and link to issues from the payload."""
        query = """
        MERGE (p:PR {neo4j_id: $number})
        SET p.title = $title,
            p.state = $state,
            p.merged = $merged,
            p.url = $url,
            p.created_at = $created_at,
            p.merged_at = $merged_at,
            p.session_id = $session_id
        """
        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    number=str(pr_data.get("number", "")),
                    title=pr_data.get("title", ""),
                    state=pr_data.get("state", "open"),
                    merged=bool(pr_data.get("merged", False)),
                    url=pr_data.get("html_url", ""),
                    created_at=str(pr_data.get("created_at", "")),
                    merged_at=str(pr_data.get("merged_at") or ""),
                    session_id=session_id,
                )
            logger.info(
                "PR upserted",
                extra={"pr": pr_data.get("number"), "state": pr_data.get("state")},
            )
        except Exception:
            logger.exception("Neo4j upsert_pr failed", extra={"pr": pr_data.get("number")})

    def upsert_pr_files(self, pr_number: int, files: list[str], session_id: str | None = None) -> None:
        """Link a PR to File nodes via MODIFIED relationships."""
        query = """
        MATCH (p:PR {neo4j_id: $pr_number})
        UNWIND $files AS file_path
        MERGE (f:File {path: file_path})
        SET f.session_id = $session_id
        MERGE (p)-[:MODIFIED]->(f)
        """
        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    pr_number=str(pr_number),
                    files=files,
                    session_id=session_id,
                )
            logger.info("PR files upserted", extra={"pr": pr_number, "file_count": len(files)})
        except Exception:
            logger.exception("Neo4j upsert_pr_files failed", extra={"pr": pr_number})

    def upsert_issue_affects(self, issue_number: int, feature_name: str, session_id: str | None = None) -> None:
        """Link an issue to a Feature via AFFECTS relationship."""
        query = """
        MATCH (i:Issue {neo4j_id: $issue_number})
        MERGE (f:Feature {name: $feature_name})
        SET f.session_id = $session_id
        MERGE (i)-[:AFFECTS]->(f)
        """
        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    issue_number=str(issue_number),
                    feature_name=feature_name,
                    session_id=session_id,
                )
        except Exception:
            logger.exception("Neo4j upsert_issue_affects failed", extra={"issue": issue_number})

    def get_all_feature_names(self, session_id: str | None = None) -> list[str]:
        """Fetch all unique Feature node names from Neo4j."""
        session_clause = ""
        params: dict = {}
        if session_id:
            session_clause = " WHERE n.session_id = $session_id"
            params["session_id"] = session_id
        query = f"""
        MATCH (n:Feature)
        {session_clause}
        RETURN DISTINCT n.name AS name
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, **params)
                return [record["name"] for record in result]
        except Exception as e:
            logger.error(f"Failed to fetch feature names: {e}")
            return []

    def ensure_feature(self, feature_name: str, session_id: str | None = None) -> None:
        """Create a Feature node if it doesn't exist."""
        session_assignment = ""
        params: dict = {"feature_name": feature_name}
        if session_id:
            session_assignment = " SET f.session_id = $session_id"
            params["session_id"] = session_id
        query = f"""
        MERGE (f:Feature {{name: $feature_name}})
        {session_assignment}
        """
        try:
            with self.driver.session() as session:
                session.run(query, **params)
        except Exception:
            logger.exception("Failed to ensure feature node", extra={"feature": feature_name})

    def cleanup_session(self, session_id: str) -> None:
        """Deletes only nodes tagged with `session_id`. Safe no-op for global data."""
        query = """
        MATCH (n)
        WHERE n.session_id = $session_id
        DETACH DELETE n
        """
        try:
            with self.driver.session() as session:
                session.run(query, session_id=session_id)
        except Exception:
            logger.exception("Neo4j session cleanup failed", extra={"session_id": session_id})
