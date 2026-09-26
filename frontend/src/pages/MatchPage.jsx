import { useState } from "react";
import { api } from "../api/client.js";
import Disclaimer from "../components/Disclaimer.jsx";
import ErrorMessage from "../components/ErrorMessage.jsx";
import MatchList from "../components/MatchList.jsx";
import ProductFields, { EMPTY_PRODUCT, compact } from "../components/ProductFields.jsx";

export default function MatchPage() {
  const [values, setValues] = useState(EMPTY_PRODUCT);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    try {
      setResult(await api("/match", { method: "POST", body: { ...compact(values), limit: 10 } }));
    } catch (err) {
      setError(err);
      setResult(null);
    }
  }

  return (
    <section>
      <h1>Check a product</h1>
      <form onSubmit={onSubmit} className="search-form">
        <ProductFields values={values} onChange={setValues} />
        <button type="submit">Check</button>
      </form>
      <ErrorMessage error={error} />
      {result && (
        <>
          <MatchList matches={result.matches} />
          <Disclaimer text={result.disclaimer} />
        </>
      )}
    </section>
  );
}
