import argparse
import os
import sys

from app.ai_engine.ingestion import (
    OpenAICompatibleEmbedder,
    RuleIngestionError,
    RuleIngestionPipeline,
    SupabaseRestRuleStore,
    extract_document_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Index an operator-verified official rules document in Supabase.")
    parser.add_argument("--file", required=True, help="Local PDF, HTML, Markdown, or UTF-8 text source")
    parser.add_argument("--title", required=True, help="Official document title")
    parser.add_argument("--source-url", required=True, help="Canonical HTTPS URL from the official host")
    parser.add_argument("--version", required=True, help="Published version or effective date")
    parser.add_argument("--verified-by", required=True, help="Operator identity that verified this source")
    parser.add_argument("--language", choices=("ru", "kk", "uz", "en", "other", "mixed"), required=True)
    parser.add_argument("--activate", action="store_true", help="Make this version active after successful indexing")
    args = parser.parse_args()

    try:
        allowed_hosts = os.environ.get("OFFICIAL_RULE_HOSTS", "").split(",")
        pipeline = RuleIngestionPipeline(
            SupabaseRestRuleStore.from_environment(),
            OpenAICompatibleEmbedder.from_environment(),
            allowed_hosts,
        )
        document_id = pipeline.ingest(
            document_title=args.title,
            source_url=args.source_url,
            source_version_date=args.version,
            content=extract_document_text(args.file),
            verified_by=args.verified_by,
            language=args.language,
            activate=args.activate,
        )
    except (OSError, RuleIngestionError, ValueError) as exc:
        print(f"Rule ingestion failed: {exc}", file=sys.stderr)
        return 1
    print(f"Indexed inactive document {document_id}" if not args.activate else f"Activated document {document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())