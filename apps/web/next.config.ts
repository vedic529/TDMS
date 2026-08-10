import type { NextConfig } from 'next';

/**
 * TDMS frontend configuration.
 *
 * `standalone` output keeps the production Docker image small and is the
 * documented Next.js approach for container deployment. It does not prevent a
 * future Cloudflare deployment through `@opennextjs/cloudflare`, which reads
 * the same build output.
 *
 * No hosting-provider specific features are used anywhere in the application.
 */
const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  eslint: {
    // Linting runs as its own CI step (`npm run lint`) so a lint warning never
    // silently breaks a production build.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
