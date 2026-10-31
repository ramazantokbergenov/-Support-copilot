import { BookOpen, ExternalLink, FileText, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeading } from "../components/UI";
import { getRules } from "../lib/api";
import type { RuleRecord } from "../types";

export function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [rules, setRules] = useState<RuleRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeDocument, setActiveDocument] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      getRules(query, controller.signal)
        .then((response) => setRules(response.items))
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить документы.");
        })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 220);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  const documents = useMemo(() => {
    const grouped = new Map<string, RuleRecord[]>();
    rules.forEach((rule) => grouped.set(rule.document_name, [...(grouped.get(rule.document_name) ?? []), rule]));
    return [...grouped.entries()];
  }, [rules]);
  const selectedRules = activeDocument ? documents.find(([name]) => name === activeDocument)?.[1] : null;

  return (
    <>
      <PageHeading eyebrow="ПРОВЕРЕННЫЕ ИСТОЧНИКИ" title="Knowledge Base" description="Поиск по активным, версионированным источникам правил Backend." />
      <section className="panel knowledge-panel">
        <div className="knowledge-toolbar">
          <label className="filter-search"><Search size={16} /><input onChange={(event) => { setQuery(event.target.value); setActiveDocument(null); }} placeholder="Поиск по названию, пункту или тексту правила" value={query} /></label>
          <span className="source-count"><BookOpen size={15} /> {rules.length} {rules.length === 1 ? "пункт" : "пунктов"}</span>
        </div>
        {error ? <ErrorState message={error} /> : loading ? <LoadingState label="Ищем в базе знаний" /> : rules.length === 0 ? (
          <EmptyState icon="book" title={query ? "Совпадений нет" : "В базе нет активных правил"} description={query ? "Попробуйте изменить поисковый запрос." : "Показываются только опубликованные правила с проверенным источником."} />
        ) : (
          <div className="knowledge-layout">
            <div className="document-list">
              <div className="knowledge-list-title">ДОКУМЕНТЫ <span>{documents.length}</span></div>
              {documents.map(([name, items]) => (
                <button className={`document-row${activeDocument === name ? " selected" : ""}`} key={name} onClick={() => setActiveDocument(name)} type="button">
                  <span className="document-icon"><FileText size={16} /></span><span className="document-copy"><strong>{name}</strong><small>{items.length} {items.length === 1 ? "правило" : "правила"} · {items[0]?.language}</small></span>
                  <span className="document-badge">{items.length}</span>
                </button>
              ))}
            </div>
            <div className="document-view">
              {selectedRules ? (
                <>
                  <div className="document-view-header"><div><span className="eyebrow">ДОКУМЕНТ</span><h2>{activeDocument}</h2></div><span className="source-count">{selectedRules.length} пунктов</span></div>
                  {selectedRules.map((rule) => (
                    <article className="knowledge-rule" key={`${rule.document_name}-${rule.rule_id}`}>
                      <div className="knowledge-rule-head"><span className="rule-id">{rule.rule_id}</span><span>{rule.version_or_date || "Версия не указана"}</span></div>
                      <h3>{rule.rule_title}</h3><p>{rule.rule_text}</p>
                      <div className="knowledge-rule-foot"><span>Язык: {rule.language}</span><a href={rule.source_url} rel="noreferrer" target="_blank">Оригинальный источник <ExternalLink size={13} /></a></div>
                    </article>
                  ))}
                </>
              ) : <div className="document-prompt"><BookOpen size={21} /><strong>Выберите документ</strong><span>Фрагменты и ссылки на источник появятся здесь.</span></div>}
            </div>
          </div>
        )}
      </section>
    </>
  );
}
