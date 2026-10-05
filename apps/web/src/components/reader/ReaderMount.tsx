"use client";

import dynamic from "next/dynamic";

import type { ReaderWork } from "./Reader";
import type { PageInfo } from "./model";

// The viewer draws on a canvas and touches `window` on import, so it renders on the client only.
const Reader = dynamic(() => import("./Reader").then((m) => m.Reader), {
  ssr: false,
  loading: () => <div className="min-h-[60dvh]" aria-busy="true" />,
});

export function ReaderMount(props: {
  locale: string;
  work: ReaderWork;
  pages: PageInfo[];
  initialIndex: number;
  initialQuery: string;
  signedIn: boolean;
}) {
  return <Reader {...props} />;
}
