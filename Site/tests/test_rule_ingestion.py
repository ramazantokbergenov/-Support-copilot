import unittest
from typing import Any

from app.ai_engine.ingestion import (
    RuleIngestionError,
    RuleIngestionPipeline,
    extract_document_text,
    split_numbered_rules,
)


class MemoryRuleStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.chunks: list[dict[str, Any]] = []

    def create_document(self, document: dict[str, Any]) -> str:
        self.documents["doc-1"] = dict(document)
        return "doc-1"

    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks.extend(chunks)

    def activate_document(self, document_id: str) -> None:
        title = self.documents[document_id]["document_title"]
        for document in self.documents.values():
            if document["document_title"] == title:
                document["is_active"] = False
        self.documents[document_id]["is_active"] = True

    def delete_document(self, document_id: str) -> None:
        self.documents.pop(document_id, None)
        self.chunks = [chunk for chunk in self.chunks if chunk["document_id"] != document_id]


class FixedEmbedder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, _text: str) -> list[float]:
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [0.0] * 1536


class RuleIngestionTests(unittest.TestCase):
    SOURCE = "# 1. General rules\nPlayers must follow the official rules.\n\n## 1.1 Cheating\nUse of cheats is prohibited."

    def test_splits_only_explicit_numbers_and_preserves_exact_text(self) -> None:
        chunks = split_numbered_rules(self.SOURCE)
        self.assertEqual([chunk.rule_number for chunk in chunks], ["1", "1.1"])
        self.assertIn("Use of cheats is prohibited.", chunks[1].content)

    def test_refuses_to_infer_rule_numbers(self) -> None:
        with self.assertRaises(RuleIngestionError):
            split_numbered_rules("General rules without numbered sections")

    def test_ingests_verified_version_and_activates_only_after_indexing(self) -> None:
        store = MemoryRuleStore()
        pipeline = RuleIngestionPipeline(store, FixedEmbedder(), ["grandmobile.example"])
        document_id = pipeline.ingest(
            document_title="Official rules",
            source_url="https://grandmobile.example/rules",
            source_version_date="2026-10-01",
            content=self.SOURCE,
            verified_by="support-admin",
            language="en",
            activate=True,
        )
        self.assertEqual(document_id, "doc-1")
        self.assertTrue(store.documents[document_id]["is_active"])
        self.assertEqual(store.documents[document_id]["source_version_date"], "2026-10-01")
        self.assertEqual([chunk["rule_number"] for chunk in store.chunks], ["1", "1.1"])
        self.assertEqual(store.chunks[1]["content"], split_numbered_rules(self.SOURCE)[1].content)

    def test_rejects_non_allowlisted_sources_before_writing(self) -> None:
        store = MemoryRuleStore()
        pipeline = RuleIngestionPipeline(store, FixedEmbedder(), ["grandmobile.example"])
        with self.assertRaises(RuleIngestionError):
            pipeline.ingest(
                document_title="Official rules",
                source_url="https://example.test/rules",
                source_version_date="2026-10-01",
                content=self.SOURCE,
                verified_by="support-admin",
                language="en",
            )
        self.assertEqual(store.documents, {})

    def test_embedding_failure_removes_unpublished_document(self) -> None:
        store = MemoryRuleStore()
        pipeline = RuleIngestionPipeline(store, FixedEmbedder(fail=True), ["grandmobile.example"])
        with self.assertRaises(RuntimeError):
            pipeline.ingest(
                document_title="Official rules",
                source_url="https://grandmobile.example/rules",
                source_version_date="2026-10-01",
                content=self.SOURCE,
                verified_by="support-admin",
                language="en",
                activate=True,
            )
        self.assertEqual(store.documents, {})
        self.assertEqual(store.chunks, [])

    def test_extracts_visible_html_text_without_script_content(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rules.html"
            source.write_text(
                "<h1>1. Rules</h1><p>Visible text</p><script>hidden secret</script>",
                encoding="utf-8",
            )
            extracted = extract_document_text(source)
        self.assertIn("1. Rules", extracted)
        self.assertIn("Visible text", extracted)
        self.assertNotIn("hidden secret", extracted)


if __name__ == "__main__":
    unittest.main()