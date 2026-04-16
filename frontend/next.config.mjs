/** @type {import('next').NextConfig} */
const apiBaseUrl = process.env.API_BASE_URL || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  experimental: {
    typedRoutes: true
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiBaseUrl}/api/:path*`
      },
      {
        source: "/health",
        destination: `${apiBaseUrl}/health`
      },
      {
        source: "/incidents/:path*",
        destination: `${apiBaseUrl}/incidents/:path*`
      },
      {
        source: "/upload",
        destination: `${apiBaseUrl}/upload`
      },
      {
        source: "/analyze",
        destination: `${apiBaseUrl}/analyze`
      },
      {
        source: "/ai/:path*",
        destination: `${apiBaseUrl}/ai/:path*`
      }
    ];
  }
};

export default nextConfig;
