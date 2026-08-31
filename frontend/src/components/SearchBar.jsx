import { useState } from "react";

export default function SearchBar({
  onSearch,
  onReset,
  graphData,
  loading,
  searching,
  searchError,
}) {
  const [name, setName] = useState("");
  const nodes = graphData?.nodes?.length || 0;
  const edges = graphData?.edges?.length || 0;
  const bursts = graphData?.edges?.filter((e) => e.burst).length || 0;

  async function submit(e) {
    e.preventDefault();
    await onSearch(name.trim());
  }

  return (
    <form className="search-bar" onSubmit={submit}>
      <input
        type="search"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Search a name — connected nodes light up"
        disabled={searching}
      />
      <button type="submit" className="btn amber" disabled={searching || loading}>
        {searching ? "Searching…" : "Search"}
      </button>
      <button type="button" className="btn ghost" onClick={onReset} disabled={searching}>
        Reset
      </button>
      <span className="hint">
        {loading ? "Loading…" : `${nodes} nodes · ${edges} edges · ${bursts} burst calls`}
      </span>
      {searchError && <span className="hint error-inline">{searchError}</span>}
    </form>
  );
}
