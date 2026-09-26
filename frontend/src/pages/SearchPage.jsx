import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import Disclaimer from "../components/Disclaimer.jsx";
import ErrorMessage from "../components/ErrorMessage.jsx";

export default function SearchPage() {
  const [form, setForm] = useState({ q: "", source: "", manufacturer: "", model: "" });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });

  async function onSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(await api("/recalls", { params: { ...form, limit: 20 } }));
    } catch (err) {
      setError(err);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h1>Search official recalls</h1>
      <form onSubmit={onSubmit} className="search-form">
        <label>
          Keywords
          <input value={form.q} onChange={update("q")} placeholder="air fryer overheating" />
        </label>
        <label>
          Manufacturer
          <input value={form.manufacturer} onChange={update("manufacturer")} />
        </label>
        <label>
          Model
          <input value={form.model} onChange={update("model")} />
        </label>
        <label>
          Source
          <select value={form.source} onChange={update("source")}>
            <option value="">All</option>
            <option value="cpsc">CPSC</option>
            <option value="nhtsa">NHTSA</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>
      <ErrorMessage error={error} />
      {result && (
        <>
          <p className="muted">{result.total} matching records</p>
          {result.items.length === 0 && (
            <p>No official recall records matched. This does not mean the product is safe.</p>
          )}
          <ul className="results">
            {result.items.map((item) => (
              <li key={item.id}>
                <Link to={`/recalls/${item.id}`}>{item.title}</Link>
                <span className="muted">
                  {" "}
                  {item.source?.toUpperCase?.() || item.source} · {item.recall_date || "no date"}
                </span>
              </li>
            ))}
          </ul>
          <Disclaimer text={result.disclaimer} />
        </>
      )}
    </section>
  );
}
