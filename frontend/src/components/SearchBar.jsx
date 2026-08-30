import { useState } from "react";

export default function SearchBar({ onSearch, onReset, graphData, loading }) {
  const [name, setName] = useState("");
  const nodes = graphData?.nodes?.length || 0;
  const edges = graphData?.edges?.length || 0;
  const bursts = graphData?.edges?.filter((e) => e.burst).length || 0;

  function submit(e) {
    e.preventDefault();
    onSearch(name.trim());
  }

  return (
    <form className="search-bar" onSubmit={submit}>
      <input
        type="search"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Search a name — connected nodes light up"
      />
      <button type="submit" className="btn amber">Search</button>
      <button type="button" className="btn ghost" onClick={onReset}>Reset</button>
      <span className="hint">
        {loading ? "Loading…" : `${nodes} nodes · ${edges} edges · ${bursts} burst calls`}
      </span>
    </form>
  );
}
