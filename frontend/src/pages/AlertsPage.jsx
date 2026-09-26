import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import Disclaimer from "../components/Disclaimer.jsx";
import ErrorMessage from "../components/ErrorMessage.jsx";
import { TierBadge } from "../components/MatchList.jsx";

export default function AlertsPage() {
  const { token } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/radar/alerts", { token }));
    } catch (err) {
      setError(err);
    }
  }, [token]);

  useEffect(() => {
    // Initial fetch; state is set after the awaited response, not synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function markRead(id) {
    await api(`/radar/alerts/${id}/read`, { method: "POST", token }).catch(setError);
    await load();
  }

  async function markAll() {
    await api("/radar/alerts/read-all", { method: "POST", token }).catch(setError);
    await load();
  }

  if (error) return <ErrorMessage error={error} />;
  if (!data) return <p>Loading…</p>;
  return (
    <section>
      <h1>Recall Radar</h1>
      <p className="muted">
        {data.unread} unread of {data.total}{" "}
        {data.unread > 0 && (
          <button className="link" onClick={markAll}>
            Mark all read
          </button>
        )}
      </p>
      {data.total === 0 && <p>No alerts yet. Radar checks your saved products against new recalls.</p>}
      <ul className="results">
        {data.items.map((a) => (
          <li key={a.id} className={a.read_at ? "" : "unread"}>
            <TierBadge tier={a.tier} /> <strong>{a.item.nickname}</strong>:{" "}
            <Link to={`/recalls/${a.recall.id}`}>{a.recall.title}</Link>
            {!a.read_at && (
              <button className="link" onClick={() => markRead(a.id)}>
                {" "}
                Mark read
              </button>
            )}
          </li>
        ))}
      </ul>
      <Disclaimer text={data.disclaimer} />
    </section>
  );
}
