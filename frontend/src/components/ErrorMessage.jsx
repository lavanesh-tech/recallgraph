export default function ErrorMessage({ error }) {
  if (!error) return null;
  return (
    <p className="error" role="alert">
      {error.message}
    </p>
  );
}
