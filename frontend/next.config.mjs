// Browser calls /api/* on the Next.js server, which forwards them to the Python backend.
// So there is no CORS setup, and only one URL to open in the demo.
const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",   // self-contained server for the Docker image (npm run dev is unaffected)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};
export default nextConfig;
