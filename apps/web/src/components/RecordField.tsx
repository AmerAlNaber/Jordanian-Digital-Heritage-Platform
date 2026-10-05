export function RecordField({ label, values }: { label: string; values: string[] }) {
  const shown = values.filter((v) => v && v.trim());
  if (shown.length === 0) return null;
  return (
    <>
      <dt className="label">{label}</dt>
      <dd className="m-0">{shown.join("، ")}</dd>
    </>
  );
}
