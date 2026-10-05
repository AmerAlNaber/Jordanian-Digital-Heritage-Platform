import { getPathname } from "@/i18n/routing";

export function SearchField({
  locale,
  label,
  placeholder,
  submit,
  defaultValue = "",
  compact = false,
  target = "/search",
}: {
  locale: string;
  label: string;
  placeholder: string;
  submit: string;
  defaultValue?: string;
  compact?: boolean;
  target?: "/search" | "/catalog";
}) {
  const action = getPathname({ href: target, locale: locale as "ar" | "en" });
  return (
    <form
      role="search"
      action={action}
      method="get"
      className="flex w-full max-w-[48rem] flex-col gap-2"
    >
      <label htmlFor="q" className={compact ? "sr-only" : "label"}>
        {label}
      </label>
      <div className="flex gap-2">
        <input
          id="q"
          name="q"
          type="search"
          defaultValue={defaultValue}
          placeholder={placeholder}
          autoComplete="off"
          className={`control flex-1 ${compact ? "" : "text-step-1"}`}
          dir="auto"
        />
        <button type="submit" className="control control-primary">
          {submit}
        </button>
      </div>
    </form>
  );
}
