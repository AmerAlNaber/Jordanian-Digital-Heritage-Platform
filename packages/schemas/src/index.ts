// Typed access to the API. `paths` and `components` come from the generated file; the helpers
// below name the shapes the web application uses most, so pages never hand-write a response type.
import type { components, paths } from "./generated/api";

export type { components, paths };

export type Schemas = components["schemas"];
export type WorkSummary = Schemas["WorkSummary"];
export type WorkDetail = Schemas["WorkDetail"];
export type PageSummary = Schemas["PageSummary"];
export type CollectionSummary = Schemas["CollectionSummary"];
export type CollectionDetail = Schemas["CollectionDetail"];
export type TermSummary = Schemas["TermSummary"];
export type ContentObjectOut = Schemas["ContentObjectOut"];
export type Me = Schemas["Me"];
export type Resolution = Schemas["Resolution"];
export type Problem = {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  code: string;
  request_id?: string | null;
};

export type Paginated<T> = { items: T[]; total: number; limit: number; offset: number };
