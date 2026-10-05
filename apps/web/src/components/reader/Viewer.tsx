"use client";

import OpenSeadragon from "openseadragon";
import { useEffect, useRef } from "react";

import type { OverlayRect, ViewerSource } from "./model";

export type ViewerApi = { zoomIn: () => void; zoomOut: () => void; fit: () => void };

const TILE_HEADER = "X-Jdhp-Tile";

/** info.json for a page, fetched with the token: protected pages answer nothing without it. */
async function loadInfo(url: string, token: string): Promise<Record<string, unknown> | null> {
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json", [TILE_HEADER]: token },
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * The scan on a canvas (RDR-1, RDR-3). Tiles are fetched with the session's tile token in a
 * header, so a tile URL alone fetches nothing; the token is refreshed by the heartbeat and
 * propagated to every open image. Matches are drawn as overlays: no text layer exists (CAT-4).
 */
export function Viewer({
  sources,
  overlays,
  rotation,
  tileToken,
  label,
  onApi,
}: {
  sources: ViewerSource[];
  overlays: OverlayRect[];
  rotation: number;
  tileToken: string;
  label: string;
  onApi?: (api: ViewerApi | null) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewer = useRef<OpenSeadragon.Viewer | null>(null);
  const token = useRef(tileToken);
  token.current = tileToken;
  const key = sources.map((s) => `${s.url}@${s.x}`).join("|");

  useEffect(() => {
    if (!host.current) return;
    const created = new OpenSeadragon.Viewer({
      element: host.current,
      showNavigationControl: false,
      showNavigator: false,
      loadTilesWithAjax: true,
      ajaxHeaders: { [TILE_HEADER]: token.current },
      crossOriginPolicy: false,
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true, scrollToZoom: true },
      gestureSettingsTouch: { pinchToZoom: true, flickEnabled: true, dragToPan: true },
      visibilityRatio: 0.85,
      constrainDuringPan: true,
      minZoomImageRatio: 0.7,
      maxZoomPixelRatio: 1.25,
      animationTime: 0.25,
      drawer: "canvas",
      imageSmoothingEnabled: true,
      placeholderFillStyle: "rgba(0,0,0,0)",
      maxImageCacheCount: 120,
    });
    viewer.current = created;
    onApi?.({
      zoomIn: () => created.viewport.zoomBy(1.25).applyConstraints(),
      zoomOut: () => created.viewport.zoomBy(0.8).applyConstraints(),
      fit: () => created.viewport.goHome(),
    });
    return () => {
      onApi?.(null);
      created.destroy();
      viewer.current = null;
    };
  }, [onApi]);

  useEffect(() => {
    const current = viewer.current;
    if (!current) return;
    let cancelled = false;
    current.setAjaxHeaders({ [TILE_HEADER]: token.current }, true);
    void Promise.all(sources.map((s) => loadInfo(s.url, token.current))).then((infos) => {
      if (cancelled || viewer.current !== current) return;
      const specs = sources.flatMap((s, i) => {
        const info = infos[i];
        return info ? [{ tileSource: info, x: s.x, y: 0, width: s.width }] : [];
      });
      if (specs.length > 0) current.open(specs);
      else current.close();
    });
    return () => {
      cancelled = true;
    };
    // `key` names the sources; the array identity changes on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    viewer.current?.setAjaxHeaders({ [TILE_HEADER]: tileToken }, true);
  }, [tileToken]);

  useEffect(() => {
    viewer.current?.viewport.setRotation(rotation);
  }, [rotation]);

  useEffect(() => {
    const current = viewer.current;
    if (!current) return;
    const draw = () => {
      current.clearOverlays();
      for (const rect of overlays) {
        const element = document.createElement("div");
        element.className = "reader-highlight";
        current.addOverlay({
          element,
          location: new OpenSeadragon.Rect(rect.x, rect.y, rect.width, rect.height),
        });
      }
    };
    if (current.isOpen()) draw();
    else current.addOnceHandler("open", draw);
    return () => current.removeHandler("open", draw);
  }, [overlays, key]);

  return (
    <div
      ref={host}
      className="reader-canvas h-full w-full select-none"
      role="img"
      aria-label={label}
      onContextMenu={(event) => event.preventDefault()}
    />
  );
}
