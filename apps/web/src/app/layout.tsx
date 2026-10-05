import type { ReactNode } from "react";

// The root layout is a pass-through; the [locale] layout renders <html> with lang and dir.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
