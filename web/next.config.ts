import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  allowedDevOrigins: ["192.168.*", "10.*", "172.16.*", "*.local"],
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    // On local dev / LAN self-hosting, proxy /api/* to the local FastAPI process
    // so browsers on localhost or 192.168.x.x work without --host 0.0.0.0 or CORS.
    if (process.env.VERCEL && !process.env.BACKEND_INTERNAL_URL) {
      return [];
    }
    const target = (
      process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000"
    ).replace(/\/$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
