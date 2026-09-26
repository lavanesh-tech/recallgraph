export default function Disclaimer({ text }) {
  return (
    <p className="disclaimer" role="note">
      {text ||
        "Results come from official CPSC and NHTSA recall records. No match does not mean a product is safe."}
    </p>
  );
}
