import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
    ...nextVitals,
    {
        rules: {
            "react/no-unescaped-entities": "off",
            // Existing components are not using the React Compiler. Keep its
            // migration diagnostics visible while enforcing hook-order errors.
            "react-hooks/set-state-in-effect": "warn",
            "react-hooks/immutability": "warn",
            "react-hooks/purity": "warn",
            "react-hooks/refs": "warn",
        },
    },
    globalIgnores([".next/**", "next-env.d.ts"]),
]);
