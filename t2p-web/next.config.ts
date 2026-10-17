import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the development workspace usable from both common loopback URLs.
  allowedDevOrigins: ["127.0.0.1"],
  // CI and local verification can use an isolated build directory while a
  // development server keeps the default `.next` directory open on Windows.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
