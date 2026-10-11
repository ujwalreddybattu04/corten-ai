/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
  // Turbopack (Next.js 16 default bundler) — empty config silences the
  // "webpack config without turbopack config" error. Turbopack does not
  // polyfill Node modules in browser bundles by default, so no extra
  // fallback config is needed.
  turbopack: {},
};

module.exports = nextConfig;
