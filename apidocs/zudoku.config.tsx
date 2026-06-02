import type { ZudokuConfig } from "zudoku";

// Portal served at /docs; the API Reference tab renders at /docs/api
// (apis.path "/api" is relative to basePath). Spec is a build-time file
// generated from the FastAPI app via `npm run gen-spec`.
const config: ZudokuConfig = {
  basePath: "/docs",
  site: {
    title: "TatvaCare AI Platform",
    logo: {
      src: {
        light: "/tatva-wordmark-light.svg",
        dark: "/tatva-wordmark-dark.svg",
      },
      alt: "TatvaCare AI Platform",
      width: "200px",
    },
    showPoweredBy: false,
  },
  metadata: {
    favicon: "/tatva_logo.jpeg",
    defaultTitle: "TatvaCare AI Platform",
    title: "%s — TatvaCare AI Platform",
  },
  navigation: [
    {
      type: "category",
      label: "Documentation",
      items: [
        {
          type: "category",
          label: "Start here",
          items: ["introduction", "getting-started"],
        },
        {
          type: "category",
          label: "Evaluations",
          items: [
            "concepts/evaluations",
            "guides/run-an-evaluation",
          ],
        },
        {
          type: "category",
          label: "Workflows & orchestration",
          items: [
            "concepts/workflows",
            "guides/build-a-workflow",
            "guides/configure-nodes",
            "guides/connect-a-provider",
            "guides/connect-a-crm",
            "concepts/datasets",
            "guides/upload-a-dataset",
          ],
        },
        {
          type: "category",
          label: "The assistant",
          items: [
            "concepts/sherlock",
            "guides/use-sherlock",
          ],
        },
        {
          type: "category",
          label: "Platform",
          items: [
            "architecture/overview",
            "architecture/data-model",
            "architecture/llm-providers",
            "concepts/tenancy-access",
          ],
        },
      ],
    },
    { type: "link", to: "/api", label: "API Reference" },
  ],
  search: { type: "pagefind" },
  redirects: [{ from: "/", to: "/introduction" }],
  apis: {
    type: "file",
    input: "./apis/openapi.json",
    path: "/api",
  },
  docs: {
    files: "/pages/**/*.{md,mdx}",
    // Machine-readable export so AI tools / an MCP server can consume the docs.
    publishMarkdown: true,
    llms: {
      llmsTxt: true,
      llmsTxtFull: true,
    },
  },
};

export default config;
