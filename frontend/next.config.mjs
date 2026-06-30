/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep Node-only RAG libs out of the webpack bundle (they use fs/Buffer and
  // break when bundled). They run only in the nodejs route handlers.
  serverExternalPackages: [
    "pdfjs-dist",
    "mammoth",
    "@langchain/community",
  ],
};

export default nextConfig;
