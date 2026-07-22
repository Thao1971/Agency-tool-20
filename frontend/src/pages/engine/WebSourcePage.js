import ResultsPage from '@/pages/ResultsPage';

/**
 * Web Source — list of agency_results indexed by the Intelligence Engine.
 * Thin wrapper that reuses the existing ResultsPage which already lists scrapes.
 */
export default function WebSourcePage() {
  return (
    <div data-testid="engine-web-source-page">
      <div className="mb-4">
        <h1 className="text-lg font-bold text-zinc-100">Intelligence Engine — Web Source</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Resultados de scrape + clasificación LLM persistidos en agency_results · enlazados al master</p>
      </div>
      <ResultsPage />
    </div>
  );
}
