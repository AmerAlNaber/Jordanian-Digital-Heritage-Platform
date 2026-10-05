// Build tokens.json into CSS custom properties and a Tailwind preset. No dependencies.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const tokens = JSON.parse(readFileSync(join(root, "tokens.json"), "utf8"));
const dist = join(root, "dist");
mkdirSync(dist, { recursive: true });

const px = (rem) => rem;
function fluid(step) {
  // clamp(min, preferred, max): preferred grows linearly between 360px and 1440px viewports.
  const min = Number.parseFloat(step.min);
  const max = Number.parseFloat(step.max);
  const slope = ((max - min) * 16) / (1440 - 360); // rem per px of viewport
  const intercept = min - slope * (360 / 16);
  return `clamp(${step.min}, ${intercept.toFixed(4)}rem + ${(slope * 100).toFixed(4)}vw, ${step.max})`;
}

function colorVars(mode) {
  return Object.entries(tokens.color[mode])
    .map(([name, value]) => `  --color-${name}: ${value};`)
    .join("\n");
}

const typeVars = Object.entries(tokens.type.steps)
  .map(([step, def]) => {
    const name = step.startsWith("-") ? `n${step.slice(1)}` : step;
    return `  --text-${name}: ${fluid(def)};\n  --leading-${name}: ${def.line};`;
  })
  .join("\n");

const spaceVars = tokens.space.scale
  .map((n) => `  --space-${n}: ${(n * tokens.space.unit) / 16}rem;`)
  .join("\n");
const sectionVars = tokens.space.section.map((n) => `  --section-${n}: ${n / 16}rem;`).join("\n");

const css = `/* Generated from tokens.json by @jdhp/design-tokens. Do not edit by hand. */
:root {
  color-scheme: light dark;
${colorVars("light")}
  --font-arabic-text: ${tokens.font["arabic-text"]};
  --font-arabic-display: ${tokens.font["arabic-display"]};
  --font-latin-text: ${tokens.font["latin-text"]};
  --font-interface: ${tokens.font.interface};
  --font-mono: ${tokens.font.mono};
${typeVars}
  --text-reading: var(--text-${tokens.type["reading-step"]});
  --leading-reading: var(--leading-${tokens.type["reading-step"]});
  --arabic-scale: ${tokens.type["arabic-scale"]};
  --measure: ${tokens.type.measure};
${spaceVars}
${sectionVars}
  --radius-control: ${tokens.radius.control};
  --radius-frame: ${tokens.radius.frame};
  --radius-image: ${tokens.radius.image};
  --radius-pill: ${tokens.radius.pill};
  --elevation-none: ${tokens.elevation.none};
  --elevation-toolbar: ${tokens.elevation.toolbar};
  --hairline: ${tokens.hairline.width} solid var(--color-hairline);
  --motion-fade: ${tokens.motion.fade};
  --motion-page-turn: ${tokens.motion["page-turn"]};
  --motion-easing: ${tokens.motion.easing};
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
${colorVars("dark")}
  }
}
:root[data-theme="dark"] {
${colorVars("dark")}
}
@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-fade: 0ms;
    --motion-page-turn: 0ms;
  }
}
`;
writeFileSync(join(dist, "tokens.css"), css);

const colorNames = Object.keys(tokens.color.light);
const preset = `// Generated from tokens.json by @jdhp/design-tokens. Do not edit by hand.
module.exports = {
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
${colorNames.map((n) => `      "${n}": "var(--color-${n})",`).join("\n")}
    },
    fontFamily: {
      "arabic-text": "var(--font-arabic-text)",
      "arabic-display": "var(--font-arabic-display)",
      "latin-text": "var(--font-latin-text)",
      interface: "var(--font-interface)",
      mono: "var(--font-mono)",
    },
    fontSize: {
${Object.keys(tokens.type.steps)
  .map((s) => {
    const name = s.startsWith("-") ? `n${s.slice(1)}` : s;
    return `      "step-${name}": ["var(--text-${name})", { lineHeight: "var(--leading-${name})" }],`;
  })
  .join("\n")}
      reading: ["var(--text-reading)", { lineHeight: "var(--leading-reading)" }],
    },
    spacing: {
      px: "1px",
${tokens.space.scale.map((n) => `      "${n}": "var(--space-${n})",`).join("\n")}
${tokens.space.section.map((n) => `      "section-${n}": "var(--section-${n})",`).join("\n")}
    },
    borderRadius: {
      none: "0",
      control: "var(--radius-control)",
      frame: "var(--radius-frame)",
      image: "var(--radius-image)",
      pill: "var(--radius-pill)",
    },
    boxShadow: {
      none: "none",
      toolbar: "var(--elevation-toolbar)",
    },
    screens: ${JSON.stringify(tokens.breakpoints, null, 6).replace(/\n/g, "\n    ")},
    extend: {
      maxWidth: { measure: "var(--measure)" },
      borderWidth: { hairline: "1px" },
      transitionDuration: { fade: "var(--motion-fade)", "page-turn": "var(--motion-page-turn)" },
      transitionTimingFunction: { jdhp: "var(--motion-easing)" },
    },
  },
};
`;
writeFileSync(join(dist, "tailwind.preset.cjs"), preset);
writeFileSync(join(dist, "tokens.json"), JSON.stringify(tokens, null, 2) + "\n");
console.log(
  `tokens built: ${colorNames.length} colors, ${Object.keys(tokens.type.steps).length} type steps`,
);
