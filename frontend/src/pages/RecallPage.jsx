import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client.js";
import Disclaimer from "../components/Disclaimer.jsx";
import ErrorMessage from "../components/ErrorMessage.jsx";

export default function RecallPage() {
  const { id } = useParams();
  const [recall, setRecall] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    api(`/recalls/${encodeURIComponent(id)}`, { signal: controller.signal })
      .then(setRecall)
      .catch((err) => err.name !== "AbortError" && setError(err));
    return () => controller.abort();
  }, [id]);

  if (error) return <ErrorMessage error={error} />;
  if (!recall) return <p>Loading…</p>;
  const list = (items, key) => (items || []).map((x, i) => <li key={i}>{x[key] ?? x}</li>);

  return (
    <article>
      <h1>{recall.title}</h1>
      <p className="muted">
        {recall.recall_date || "no date"} · source record {recall.source_record_id}
      </p>
      {recall.description && <p>{recall.description}</p>}
      <h2>Products</h2>
      <ul>{list(recall.products, "name")}</ul>
      <h2>Hazards</h2>
      <ul>{list(recall.hazards, "description")}</ul>
      <h2>Remedies</h2>
      <ul>{list(recall.remedies, "description")}</ul>
      <Disclaimer text={recall.disclaimer} />
    </article>
  );
}
