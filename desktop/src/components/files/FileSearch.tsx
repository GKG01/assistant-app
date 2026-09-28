import { useState } from "react";
import { indexFiles, openFile, searchFiles, showInFolder } from "../../services/api";
import type { IndexStats, SearchFilters, SearchResponse } from "../../types/api";
import { FileResultCard } from "./FileResultCard";

const PAGE_SIZE = 20;

export function FileSearch() {
  const [q, setQ] = useState("");
  const [extension, setExtension] = useState("");
  const [sort, setSort] = useState<SearchFilters["sort"]>("modified_desc");
  const [activeFilters, setActiveFilters] = useState<SearchFilters>({});
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [stats, setStats] = useState<IndexStats | null>(null);
  const [busy, setBusy] = useState<"search" | "index" | "action" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load(filters: SearchFilters) {
    const response = await searchFiles(filters);
    setResults(response);
    setActiveFilters(filters);
  }

  async function search(offset = 0, paginate = false) {
    setBusy("search");
    setError("");
    setNotice("");
    try {
      await load(paginate ? { ...activeFilters, offset } : { q, extension, sort, limit: PAGE_SIZE, offset });
    } catch (error) {
      setError(error instanceof Error ? error.message : "Search failed.");
    } finally { setBusy(null); }
  }

  async function refresh() {
    setBusy("index");
    setStats(null);
    setError("");
    setNotice("");
    try {
      const result = await indexFiles();
      setStats(result);
      await load({ q, extension, sort, limit: PAGE_SIZE, offset: 0 });
    } catch (error) {
      setError(error instanceof Error ? error.message : "Refresh failed.");
    } finally { setBusy(null); }
  }

  async function act(id: number, action: "open" | "reveal") {
    setBusy("action");
    setError("");
    setNotice("");
    try {
      if (action === "open") await openFile(id);
      else await showInFolder(id);
      setNotice(action === "open" ? "Open request sent to Windows." : "Reveal request sent to Windows.");
    } catch (error) {
      setError(error instanceof Error ? error.message : "File action failed.");
    } finally { setBusy(null); }
  }

  const inputClass = "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:outline-teal-400";
  return (
    <section className="flex-1 py-8" aria-labelledby="files-heading" aria-busy={busy !== null}>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="files-heading" className="text-2xl font-medium">Find your files</h2>
          <p className="mt-1 text-sm text-slate-400">Search filenames in your configured folders. No AI required.</p>
        </div>
        <button className="button bg-teal-900 hover:bg-teal-800" disabled={busy !== null} onClick={() => void refresh()}>
          {busy === "index" ? "Indexing…" : "Refresh Files"}
        </button>
      </div>
      <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); if (!busy) void search(); }}>
        <input className={`${inputClass} min-w-40 flex-1`} aria-label="Search filenames"
          placeholder="Search filenames, e.g. resume" value={q} maxLength={500}
          onChange={(event) => setQ(event.target.value)} disabled={busy !== null} />
        <input className={`${inputClass} w-28`} aria-label="Extension filter"
          placeholder=".pdf" value={extension} maxLength={30}
          onChange={(event) => setExtension(event.target.value)} disabled={busy !== null} />
        <select className={inputClass} aria-label="Sort results" value={sort}
          disabled={busy !== null} onChange={(event) => setSort(event.target.value as SearchFilters["sort"])}>
          <option value="modified_desc">Newest modified</option><option value="modified_asc">Oldest modified</option>
          <option value="name_asc">Name A–Z</option><option value="name_desc">Name Z–A</option>
          <option value="size_desc">Largest first</option><option value="size_asc">Smallest first</option>
        </select>
        <button className="button bg-slate-700 hover:bg-slate-600" disabled={busy !== null} type="submit">Search</button>
      </form>
      <div className="my-4 text-sm" role="status" aria-live="polite">
        {busy === "index" && <p>Scanning configured directories. Large folders may take a while.</p>}
        {busy === "search" && <p>Searching the index…</p>}
        {busy === "action" && <p>Requesting Windows action…</p>}
        {stats && <p>Refresh {stats.roots_failed ? "partially completed" : "complete"}: {stats.indexed.toLocaleString()} indexed · {stats.created} new · {stats.updated} updated · {stats.unchanged} unchanged · {stats.removed} removed · {stats.skipped} skipped ({stats.duration_ms} ms)</p>}
        {stats?.warnings.map((warning, index) => <p key={index} className="mt-1 text-amber-300">{warning}</p>)}
        {notice && <p>{notice}</p>}
      </div>
      {error && <p role="alert" className="my-4 rounded-lg border border-red-900 bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {!results && !busy && <p className="py-12 text-center text-slate-400">Configure your folders in .env, then click Refresh Files. If already indexed, use Search.</p>}
      {results && <>
        <p className="mb-3 text-sm text-slate-400">{results.total.toLocaleString()} matching files</p>
        {results.results.length === 0
          ? <p className="py-10 text-center text-slate-400">No matching files. Try another search or refresh your index.</p>
          : <ul className="space-y-3">{results.results.map((file) =>
            <FileResultCard key={file.id} file={file} busy={busy !== null} onAction={(id, action) => void act(id, action)} />)}</ul>}
        <div className="mt-4 flex items-center justify-between">
          <button className="button bg-slate-800" disabled={busy !== null || results.offset === 0}
            onClick={() => void search(Math.max(0, results.offset - PAGE_SIZE), true)}>Previous</button>
          <span className="text-xs text-slate-400">{results.total > 0 ? `${results.offset + 1}–${results.offset + results.results.length}` : "0"} of {results.total}</span>
          <button className="button bg-slate-800" disabled={busy !== null || results.offset + results.limit >= results.total}
            onClick={() => void search(results.offset + PAGE_SIZE, true)}>Next</button>
        </div>
      </>}
      <p className="mt-6 text-xs text-slate-500">Open supports selected document/image types. Windows-native backend required for Open and Show in Folder.</p>
    </section>
  );
}
