import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output for the production Docker image (multi-stage build
  // copies only the traced server bundle, not the full node_modules tree).
  output: "standalone",
};

export default nextConfig;
