import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Traces and copies only the node_modules entries actually needed at
  // runtime into .next/standalone (ADR-019 decision 4) — the Docker image
  // doesn't need devDependencies like the openapi-typescript CLI.
  output: "standalone",
  // Standard security headers (ADR-020) — genuinely absent before Phase 17.
  // Applied here rather than only on the backend, since this is the
  // actual user-facing HTML people load in a browser.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "geolocation=(), camera=(), microphone=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
