// The parts of OpenSeadragon 5 the reader uses. The library ships no type definitions.
declare module "openseadragon" {
  namespace OpenSeadragon {
    class Point {
      constructor(x?: number, y?: number);
      x: number;
      y: number;
    }
    class Rect {
      constructor(x?: number, y?: number, width?: number, height?: number, degrees?: number);
      x: number;
      y: number;
      width: number;
      height: number;
    }
    interface TiledImageSpec {
      tileSource: string | Record<string, unknown>;
      x?: number;
      y?: number;
      width?: number;
      height?: number;
    }
    interface GestureSettings {
      scrollToZoom?: boolean;
      clickToZoom?: boolean;
      dblClickToZoom?: boolean;
      dragToPan?: boolean;
      pinchToZoom?: boolean;
      flickEnabled?: boolean;
    }
    interface Options {
      element?: HTMLElement;
      id?: string;
      tileSources?: string | Record<string, unknown> | Array<string | TiledImageSpec>;
      showNavigationControl?: boolean;
      showNavigator?: boolean;
      sequenceMode?: boolean;
      loadTilesWithAjax?: boolean;
      ajaxHeaders?: Record<string, string>;
      crossOriginPolicy?: string | false;
      gestureSettingsMouse?: GestureSettings;
      gestureSettingsTouch?: GestureSettings;
      visibilityRatio?: number;
      constrainDuringPan?: boolean;
      minZoomImageRatio?: number;
      maxZoomPixelRatio?: number;
      animationTime?: number;
      springStiffness?: number;
      drawer?: string;
      imageSmoothingEnabled?: boolean;
      preserveViewport?: boolean;
      homeFillsViewer?: boolean;
      placeholderFillStyle?: string;
      zoomPerScroll?: number;
      zoomPerClick?: number;
      defaultZoomLevel?: number;
      smoothTileEdgesMinZoom?: number;
      maxImageCacheCount?: number;
      ajaxWithCredentials?: boolean;
      autoHideControls?: boolean;
    }
    class TiledImage {
      imageToViewportRectangle(x: number, y: number, width: number, height: number): Rect;
      getBounds(): Rect;
    }
    class World {
      getItemCount(): number;
      getItemAt(index: number): TiledImage;
      getHomeBounds(): Rect;
    }
    class Viewport {
      setRotation(degrees: number, immediately?: boolean): Viewport;
      getRotation(): number;
      zoomBy(factor: number, refPoint?: Point, immediately?: boolean): Viewport;
      applyConstraints(immediately?: boolean): Viewport;
      goHome(immediately?: boolean): Viewport;
      fitBounds(bounds: Rect, immediately?: boolean): Viewport;
      getZoom(current?: boolean): number;
    }
    interface OverlaySpec {
      element: HTMLElement;
      location: Rect | Point;
      checkResize?: boolean;
    }
    type Handler = (event: Record<string, unknown>) => void;
    class Viewer {
      constructor(options: Options);
      world: World;
      viewport: Viewport;
      element: HTMLElement;
      canvas: HTMLElement;
      open(source: string | Record<string, unknown> | Array<string | TiledImageSpec>): Viewer;
      close(): Viewer;
      destroy(): void;
      isOpen(): boolean;
      addHandler(eventName: string, handler: Handler): void;
      removeHandler(eventName: string, handler: Handler): void;
      addOnceHandler(eventName: string, handler: Handler): void;
      addOverlay(spec: OverlaySpec): Viewer;
      removeOverlay(element: HTMLElement | string): Viewer;
      clearOverlays(): Viewer;
      setAjaxHeaders(headers: Record<string, string>, propagate?: boolean): void;
      forceRedraw(): Viewer;
    }
  }
  function OpenSeadragon(options: OpenSeadragon.Options): OpenSeadragon.Viewer;
  export = OpenSeadragon;
}
