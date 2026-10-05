import localFont from "next/font/local";

// Self-hosted faces chosen in docs/DESIGN.md (ADR-0001 D14). Subsetting per script is a build
// step for Phase 1 (PRF-5); the variable files are loaded with display: swap and preloaded.
export const amiri = localFont({
  src: [
    { path: "../../public/fonts/amiri/Amiri-Regular.ttf", weight: "400", style: "normal" },
    { path: "../../public/fonts/amiri/Amiri-Bold.ttf", weight: "700", style: "normal" },
  ],
  variable: "--font-amiri",
  display: "swap",
  preload: true,
});

export const notoKufi = localFont({
  src: [
    {
      path: "../../public/fonts/notokufiarabic/NotoKufiArabic[wght].ttf",
      weight: "100 900",
      style: "normal",
    },
  ],
  variable: "--font-noto-kufi",
  display: "swap",
  preload: true,
});

export const crimson = localFont({
  src: [
    {
      path: "../../public/fonts/crimsonpro/CrimsonPro[wght].ttf",
      weight: "200 900",
      style: "normal",
    },
    {
      path: "../../public/fonts/crimsonpro/CrimsonPro-Italic[wght].ttf",
      weight: "200 900",
      style: "italic",
    },
  ],
  variable: "--font-crimson",
  display: "swap",
  preload: false,
});

export const plexArabic = localFont({
  src: [
    {
      path: "../../public/fonts/ibmplexsansarabic/IBMPlexSansArabic-Regular.ttf",
      weight: "400",
      style: "normal",
    },
    {
      path: "../../public/fonts/ibmplexsansarabic/IBMPlexSansArabic-Medium.ttf",
      weight: "500",
      style: "normal",
    },
    {
      path: "../../public/fonts/ibmplexsansarabic/IBMPlexSansArabic-SemiBold.ttf",
      weight: "600",
      style: "normal",
    },
  ],
  variable: "--font-plex-arabic",
  display: "swap",
  preload: true,
});

export const fontClassName = [
  amiri.variable,
  notoKufi.variable,
  crimson.variable,
  plexArabic.variable,
].join(" ");
