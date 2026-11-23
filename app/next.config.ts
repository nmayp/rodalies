import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // the API route reads the timetable files from disk, so make sure they ship with it
  outputFileTracingIncludes: { "/api/trains": ["./public/trains/**/*"] },
};

export default nextConfig;
