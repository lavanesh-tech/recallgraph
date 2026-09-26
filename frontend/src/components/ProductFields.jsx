export const EMPTY_PRODUCT = { description: "", manufacturer: "", model: "", upc: "" };

// Drops empty strings so the API never receives "" for optional fields.
export function compact(values) {
  return Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
}

export default function ProductFields({ values, onChange }) {
  const field = (name, label, props = {}) => (
    <label>
      {label}
      <input value={values[name]} onChange={(e) => onChange({ ...values, [name]: e.target.value })} {...props} />
    </label>
  );
  return (
    <>
      {field("description", "Description", { placeholder: "stainless air fryer" })}
      {field("manufacturer", "Manufacturer")}
      {field("model", "Model")}
      {field("upc", "UPC", { inputMode: "numeric", pattern: "\\d{8,14}" })}
    </>
  );
}
