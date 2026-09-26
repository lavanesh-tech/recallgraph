import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ErrorMessage from "../components/ErrorMessage.jsx";
import MatchList from "../components/MatchList.jsx";
import ProductFields, { EMPTY_PRODUCT, compact } from "../components/ProductFields.jsx";

export default function InventoryPage() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [nickname, setNickname] = useState("");
  const [values, setValues] = useState(EMPTY_PRODUCT);
  const [matches, setMatches] = useState({});
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setItems((await api("/inventory", { token })).items);
    } catch (err) {
      setError(err);
    }
  }, [token]);

  useEffect(() => {
    // Initial fetch; state is set after the awaited response, not synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function add(event) {
    event.preventDefault();
    setError(null);
    try {
      await api("/inventory", { method: "POST", token, body: { nickname, ...compact(values) } });
      setNickname("");
      setValues(EMPTY_PRODUCT);
      await load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id) {
    await api(`/inventory/${id}`, { method: "DELETE", token }).catch(setError);
    await load();
  }

  async function check(id) {
    try {
      const result = await api(`/inventory/${id}/matches`, { token });
      setMatches((m) => ({ ...m, [id]: result.matches }));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <h1>My products</h1>
      <form onSubmit={add} className="search-form">
        <label>
          Nickname
          <input required value={nickname} onChange={(e) => setNickname(e.target.value)} />
        </label>
        <ProductFields values={values} onChange={setValues} />
        <button type="submit">Add</button>
      </form>
      <ErrorMessage error={error} />
      {items.length === 0 && <p className="muted">No saved products yet.</p>}
      <ul className="results">
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.nickname}</strong>{" "}
            <span className="muted">
              {[item.manufacturer, item.model, item.upc, item.description].filter(Boolean).join(" · ")}
            </span>
            <div className="row">
              <button onClick={() => check(item.id)}>Check recalls</button>
              <button className="link" onClick={() => remove(item.id)} aria-label={`Delete ${item.nickname}`}>
                Delete
              </button>
            </div>
            {matches[item.id] && <MatchList matches={matches[item.id]} />}
          </li>
        ))}
      </ul>
    </section>
  );
}
