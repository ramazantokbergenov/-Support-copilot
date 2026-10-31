import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader


MAX_RULE_CHUNK_CHARACTERS = 8_000
RULE_HEADER_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?:rule\s+|пункт\s*)?"
    r"(\d+(?:\.\d+)+(?:[.)])?|\d+[.)])\s+(.+?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RuleChunk:
    rule_number: str
    title: str
    content: str


class RuleIndexStore(Protocol):
    def create_document(self, document: dict[str, Any]) -> str: ...
    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None: ...
    def activate_document(self, document_id: str) -> None: ...
    def delete_document(self, document_id: str) -> None: ...


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class RuleIngestionError(ValueError):
    pass


def split_numbered_rules(text: str) -> list[RuleChunk]:
    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, str, str]] = []
    offset = 0
    for line in lines:
        match = RULE_HEADER_RE.match(line.rstrip("\r\n"))
        if match:
            number = match.group(1).rstrip(".)")
            starts.append((offset, number, match.group(2).strip()))
        offset += len(line)
    if not starts:
        raise RuleIngestionError(
            "No explicit numbered sections found; rule numbers will not be inferred."
        )

    chunks: list[RuleChunk] = []
    seen: set[str] = set()
    for index, (start, number, title) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        content = text[start:end].strip()
        if number in seen:
            raise RuleIngestionError(f"Duplicate rule number in source: {number}")
        if len(content) > MAX_RULE_CHUNK_CHARACTERS:
            raise RuleIngestionError(
                f"Rule {number} exceeds {MAX_RULE_CHUNK_CHARACTERS} characters; "
                "split it at an explicit subsection in the source."
            )
        if content:
            chunks.append(RuleChunk(number, title, content))
            seen.add(number)
    return chunks


class _VisibleTextParser(HTMLParser):
    _BLOCK_TAGS = {"address", "article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        elif tag in self._BLOCK_TAGS and not self.hidden_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in self._BLOCK_TAGS and not self.hidden_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def extract_document_text(path: str | Path) -> str:
    source = Path(path)
    suffix = source.suffix.casefold()
    if suffix == ".pdf":
        reader = PdfReader(str(source))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix in {".html", ".htm"}:
        parser = _VisibleTextParser()
        parser.feed(source.read_text(encoding="utf-8"))
        text = "".join(parser.parts)
    elif suffix in {".txt", ".md", ".markdown"}:
        text = source.read_text(encoding="utf-8")
    else:
        raise RuleIngestionError("Supported rule files are PDF, HTML, Markdown, and UTF-8 text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise RuleIngestionError("No readable text was extracted from the source file.")
    return text


class SupabaseRestRuleStore:
    def __init__(self, *, url: str, service_role_key: str, timeout: float = 30) -> None:
        self.url = url.rstrip("/")
        self.key = service_role_key
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> "SupabaseRestRuleStore":
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise RuleIngestionError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
        return cls(url=url, service_role_key=key)

    def _request(self, method: str, path: str, body: Any = None, prefer: str = "") -> Any:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(f"{self.url}/rest/v1/{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuleIngestionError("Supabase rule index request failed.") from exc
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuleIngestionError("Supabase returned an invalid response.") from exc

    def create_document(self, document: dict[str, Any]) -> str:
        rows = self._request("POST", "rule_documents", document, "return=representation")
        if not isinstance(rows, list) or not rows or not rows[0].get("id"):
            raise RuleIngestionError("Supabase did not return the new document id.")
        return str(rows[0]["id"])

    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        for start in range(0, len(chunks), 50):
            self._request("POST", "rule_chunks", chunks[start:start + 50], "return=minimal")

    def activate_document(self, document_id: str) -> None:
        self._request("POST", "rpc/activate_rule_document", {"target_document_id": document_id})

    def delete_document(self, document_id: str) -> None:
        filters = urlencode({"id": f"eq.{document_id}"})
        self._request("DELETE", f"rule_documents?{filters}")


class OpenAICompatibleEmbedder:
    def __init__(self, *, base_url: str, api_key: str, model: str, dimensions: int = 1536) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleEmbedder":
        base_url = os.environ.get("LLM_API_BASE_URL", "https://api.openai.com/v1").strip()
        api_key = os.environ.get("LLM_API_KEY", "").strip()
        model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small").strip()
        if not api_key or not model:
            raise RuleIngestionError("LLM_API_KEY and EMBEDDING_MODEL are required.")
        if not base_url.startswith(("https://", "http://")):
            raise RuleIngestionError("LLM_API_BASE_URL must use HTTP or HTTPS.")
        return cls(base_url=base_url, api_key=api_key, model=model)

    def embed(self, text: str) -> list[float]:
        request_body = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        request = Request(
            f"{self.base_url}/embeddings",
            data=request_body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            vector = payload["data"][0]["embedding"]
        except (HTTPError, URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuleIngestionError("The embedding provider request failed.") from exc
        if not isinstance(vector, list) or len(vector) != self.dimensions:
            raise RuleIngestionError(f"Embeddings must contain {self.dimensions} dimensions.")
        if not all(isinstance(value, (int, float)) for value in vector):
            raise RuleIngestionError("The embedding provider returned non-numeric values.")
        return [float(value) for value in vector]


class RuleIngestionPipeline:
    def __init__(
        self,
        store: RuleIndexStore,
        embedder: Embedder,
        allowed_hosts: Iterable[str],
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.allowed_hosts = {host.strip().casefold().lstrip(".") for host in allowed_hosts if host.strip()}

    def ingest(
        self,
        *,
        document_title: str,
        source_url: str,
        source_version_date: str,
        content: str,
        verified_by: str,
        language: str,
        activate: bool = False,
    ) -> str:
        title = document_title.strip()
        version = source_version_date.strip()
        reviewer = verified_by.strip()
        parsed_url = urlparse(source_url.strip())
        host = (parsed_url.hostname or "").casefold()
        if not title or not version or not reviewer:
            raise RuleIngestionError("Document title, source version date, and verified_by are required.")
        if parsed_url.scheme != "https" or not host or not any(
            host == allowed or host.endswith(f".{allowed}") for allowed in self.allowed_hosts
        ):
            raise RuleIngestionError("The source must use HTTPS and an allowlisted official host.")
        if language not in {"ru", "kk", "uz", "en", "other", "mixed"}:
            raise RuleIngestionError("language must be ru, kk, uz, en, other, or mixed.")
        chunks = split_numbered_rules(content)
        document_id = self.store.create_document({
            "document_title": title,
            "source_url": source_url.strip(),
            "source_version_date": version,
            "content": content,
            "is_active": False,
            "verified_by": reviewer,
        })
        try:
            indexed_chunks = []
            for chunk in chunks:
                indexed_chunks.append({
                    "document_id": document_id,
                    "rule_number": chunk.rule_number,
                    "content": chunk.content,
                    "embedding": self.embedder.embed(chunk.content),
                    "metadata": {"title": chunk.title, "language": language},
                })
            self.store.insert_chunks(indexed_chunks)
            if activate:
                self.store.activate_document(document_id)
        except Exception:
            self.store.delete_document(document_id)
            raise
        return document_id