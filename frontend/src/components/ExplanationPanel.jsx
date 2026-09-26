import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ErrorMessage from "./ErrorMessage.jsx";

// Shows the explanation next to the exact evidence it cites (E1, E2...).
export default function ExplanationPanel({ recallId }) {
  const { token } = useAuth();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!token) {
    return (
      <p className="muted">
        <Link to="/login">Sign in</Link> to get a plain-language explanation.
      </p>
    );
  }

  async function onSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const body = question.trim() ? { question: question.trim() } : {};
      setResult(await api(`/recalls/${recallId}/explanation`, { method: "POST", token, body }));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>Explain this recall</h2>
      <form onSubmit={onSubmit}>
        <label>
          Question (optional)
          <input maxLength={300} value={question} onChange={(e) => setQuestion(e.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Explaining…" : "Explain"}
        </button>
      </form>
      <ErrorMessage error={error} />
      {result && (
        <div>
          <p>
            <strong>{result.summary}</strong>{" "}
            <span className="muted">
              ({result.mode === "llm" ? `AI-worded, ${result.model}` : "template from official record"})
            </span>
          </p>
          {result.insufficient_evidence && (
            <p className="disclaimer">The official record does not answer that question.</p>
          )}
          <ul>
            {result.points.map((p, i) => (
              <li key={i}>
                {p.text} <span className="cite">[{p.citations.join(", ")}]</span>
              </li>
            ))}
          </ul>
          <details>
            <summary>Evidence</summary>
            <ol className="evidence">
              {result.evidence.map((e) => (
                <li key={e.id} value={Number(e.id.slice(1))}>
                  <span className="cite">{e.id}</span> ({e.kind}) {e.text}
                </li>
              ))}
            </ol>
          </details>
          <p className="disclaimer">{result.disclaimer}</p>
        </div>
      )}
    </section>
  );
}
