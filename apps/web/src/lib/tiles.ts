// Where the browser fetches tiles and where it calls the API. Both are same-origin paths behind
// Caddy in every deployment; the variables exist for development without the proxy.
export function tilesBase(): string {
  return (process.env.NEXT_PUBLIC_TILES_URL ?? "/iiif/3").replace(/\/$/, "");
}

export function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/$/, "");
}

/** The IIIF identifier of a page: the work's public name and the page number, never a row id. */
export function pageIdentifier(work: string, seq: number): string {
  return `${work}-p${String(seq).padStart(4, "0")}`;
}

export function infoUrl(work: string, seq: number): string {
  return `${tilesBase()}/${pageIdentifier(work, seq)}/info.json`;
}

/** A small rendering of a page through the authorizing gateway. Public for sample pages. */
export function thumbnailUrl(work: string, seq: number, height = 160): string {
  return `${tilesBase()}/${pageIdentifier(work, seq)}/full/,${height}/0/default.webp`;
}

/** Whether a page's scan can be fetched without a reader session (the sample range). */
export function publiclyViewable(seq: number, samplePageLimit: number | null): boolean {
  return samplePageLimit === null || seq <= samplePageLimit;
}
