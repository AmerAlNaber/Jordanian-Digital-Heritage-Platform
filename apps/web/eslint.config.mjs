import { FlatCompat } from "@eslint/eslintrc";
import js from "@eslint/js";
import security from "eslint-plugin-security";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  js.configs.recommended,
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  security.configs.recommended,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "security/detect-object-injection": "off",
    },
  },
  { ignores: [".next/", "node_modules/", "next-env.d.ts"] },
];

export default config;
