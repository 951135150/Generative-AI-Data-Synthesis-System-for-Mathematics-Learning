import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    ".next-build/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "src/app/page - 副本.tsx",
  ]),
  {
    rules: {
      // Local-storage hydration and defensive cache repair intentionally update
      // state from effects after the browser environment becomes available.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
