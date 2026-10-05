// OKLCH to sRGB and WCAG contrast, for the accessibility test (ACX-4). Pure functions.
export function parseOklch(value) {
  const m = value.match(/oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\s*\)/);
  if (!m) throw new Error(`not an oklch color: ${value}`);
  return {
    L: Number(m[1]) / 100,
    C: Number(m[2]),
    h: Number(m[3]),
    alpha: m[4] === undefined ? 1 : Number(m[4]),
  };
}

export function oklchToLinearSrgb({ L, C, h }) {
  const hr = (h * Math.PI) / 180;
  const a = C * Math.cos(hr);
  const b = C * Math.sin(hr);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;
  return {
    r: +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    g: -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    b: -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  };
}

const clamp01 = (v) => Math.min(1, Math.max(0, v));

export function relativeLuminance(oklch) {
  const { r, g, b } = oklchToLinearSrgb(parseOklch(oklch));
  return 0.2126 * clamp01(r) + 0.7152 * clamp01(g) + 0.0722 * clamp01(b);
}

export function contrast(foreground, background) {
  const l1 = relativeLuminance(foreground);
  const l2 = relativeLuminance(background);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}
