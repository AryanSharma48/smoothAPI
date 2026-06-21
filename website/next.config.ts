import type { NextConfig } from "next";
import pkg from "../packages/smooth-api-ts/package.json";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_TS_PKG_VERSION: pkg.version,
  },
};

export default nextConfig;
