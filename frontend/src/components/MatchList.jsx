import { Link } from "react-router-dom";

const TIER_LABEL = {
  identifier_match: "Identifier match",
  likely: "Likely match",
  possible: "Possible match",
};

export function TierBadge({ tier }) {
  return <span className={`tier tier-${tier}`}>{TIER_LABEL[tier] || tier}</span>;
}

// Every match shows WHY it matched: the engine's signals with their evidence.
export default function MatchList({ matches }) {
  if (!matches.length) {
    return <p>No official recall records matched. This does not mean the product is safe.</p>;
  }
  return (
    <ul className="results">
      {matches.map((m) => (
        <li key={m.recall.id}>
          <TierBadge tier={m.tier} /> <Link to={`/recalls/${m.recall.id}`}>{m.recall.title}</Link>
          <span className="muted">
            {" "}
            score {m.score.toFixed(2)} · {m.recall.recall_date || "no date"}
          </span>
          <details>
            <summary>Why this matched</summary>
            <table className="signals">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Contribution</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {m.signals
                  .filter((s) => s.applicable)
                  .map((s) => (
                    <tr key={s.name}>
                      <td>{s.name}</td>
                      <td>{s.contribution.toFixed(3)}</td>
                      <td>{Array.isArray(s.evidence) ? s.evidence.join(", ") : s.evidence}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
        </li>
      ))}
    </ul>
  );
}
