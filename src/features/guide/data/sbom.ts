export interface SbomEntry {
  name: string;
  version: string;
  license: string;
  category: 'Frontend' | 'Backend' | 'Database' | 'Infrastructure' | 'Dev Tooling';
  description: string;
}

export const sbomData: SbomEntry[] = [
  // Frontend
  { name: 'React', version: '19.x', license: 'MIT', category: 'Frontend', description: 'UI component library' },
  { name: 'React DOM', version: '19.x', license: 'MIT', category: 'Frontend', description: 'React renderer for the browser' },
  { name: 'TypeScript', version: '5.9.x', license: 'Apache-2.0', category: 'Frontend', description: 'Typed superset of JavaScript' },
  { name: 'Vite', version: '7.x', license: 'MIT', category: 'Frontend', description: 'Fast build tool and dev server' },
  { name: 'Zustand', version: '5.x', license: 'MIT', category: 'Frontend', description: 'Lightweight state management' },
  { name: 'Tailwind CSS', version: '4.x', license: 'MIT', category: 'Frontend', description: 'Utility-first CSS framework' },
  { name: 'React Router', version: '7.x', license: 'MIT', category: 'Frontend', description: 'Client-side routing' },
  { name: 'Lucide React', version: '0.563.x', license: 'ISC', category: 'Frontend', description: 'Icon library for React' },
  { name: 'Recharts', version: '3.x', license: 'MIT', category: 'Frontend', description: 'Composable charting library' },
  { name: 'date-fns', version: '4.x', license: 'MIT', category: 'Frontend', description: 'Date utility functions' },
  { name: 'clsx', version: '2.x', license: 'MIT', category: 'Frontend', description: 'Conditional className utility' },
  { name: 'tailwind-merge', version: '3.x', license: 'MIT', category: 'Frontend', description: 'Merge Tailwind classes intelligently' },
  { name: 'jsPDF', version: '4.x', license: 'MIT', category: 'Frontend', description: 'Client-side PDF generation' },
  { name: 'jspdf-autotable', version: '5.x', license: 'MIT', category: 'Frontend', description: 'PDF table generation plugin for jsPDF' },
  { name: 'react-markdown', version: '10.x', license: 'MIT', category: 'Frontend', description: 'Markdown renderer for React' },
  { name: 'remark-gfm', version: '4.x', license: 'MIT', category: 'Frontend', description: 'GitHub Flavored Markdown support for react-markdown' },
  { name: 'sonner', version: '2.x', license: 'MIT', category: 'Frontend', description: 'Toast notification library' },
  { name: 'wavesurfer.js', version: '7.x', license: 'BSD-3-Clause', category: 'Frontend', description: 'Audio waveform visualization' },
  { name: '@google/genai', version: '1.x', license: 'Apache-2.0', category: 'Frontend', description: 'Google Gemini AI SDK (frontend pipeline)' },
  { name: 'fastest-levenshtein', version: '1.x', license: 'MIT', category: 'Frontend', description: 'Fast string distance calculation' },

  // Backend
  { name: 'FastAPI', version: '0.115.x', license: 'MIT', category: 'Backend', description: 'Async Python web framework' },
  { name: 'Uvicorn', version: '0.30.x', license: 'BSD-3-Clause', category: 'Backend', description: 'ASGI server for FastAPI' },
  { name: 'SQLAlchemy', version: '2.x', license: 'MIT', category: 'Backend', description: 'Async ORM with Python type support' },
  { name: 'asyncpg', version: '0.30.x', license: 'Apache-2.0', category: 'Backend', description: 'PostgreSQL async driver' },
  { name: 'Pydantic', version: '2.x', license: 'MIT', category: 'Backend', description: 'Data validation and settings' },
  { name: 'pydantic-settings', version: '2.x', license: 'MIT', category: 'Backend', description: 'Settings management via Pydantic' },
  { name: 'Python', version: '3.12', license: 'PSF-2.0', category: 'Backend', description: 'Programming language runtime' },
  { name: 'google-genai', version: '1.x', license: 'Apache-2.0', category: 'Backend', description: 'Google Gemini AI SDK' },
  { name: 'openai', version: '1.x', license: 'Apache-2.0', category: 'Backend', description: 'OpenAI API client' },
  { name: 'anthropic', version: '0.x', license: 'MIT', category: 'Backend', description: 'Anthropic Claude API client' },
  { name: 'aiohttp', version: '3.x', license: 'Apache-2.0', category: 'Backend', description: 'Async HTTP client' },
  { name: 'python-multipart', version: '0.0.x', license: 'Apache-2.0', category: 'Backend', description: 'Multipart form data parsing' },
  { name: 'aiofiles', version: '24.x', license: 'Apache-2.0', category: 'Backend', description: 'Async file operations' },
  { name: 'PyJWT', version: '2.x', license: 'MIT', category: 'Backend', description: 'JSON Web Token implementation' },
  { name: 'bcrypt', version: '4.x', license: 'Apache-2.0', category: 'Backend', description: 'Password hashing' },
  { name: 'pandas', version: '2.x', license: 'BSD-3-Clause', category: 'Backend', description: 'Data analysis and CSV processing' },
  { name: 'Playwright', version: '1.52.x', license: 'Apache-2.0', category: 'Backend', description: 'Browser automation for PDF report export' },
  { name: 'python-dotenv', version: '1.x', license: 'BSD-3-Clause', category: 'Backend', description: 'Environment variable loading from .env files' },
  { name: 'google-auth', version: '2.x', license: 'Apache-2.0', category: 'Backend', description: 'Google service account authentication' },

  // Database
  { name: 'PostgreSQL', version: '16', license: 'PostgreSQL', category: 'Database', description: 'Relational database with JSONB support' },

  // Infrastructure
  { name: 'Docker', version: '27.x', license: 'Apache-2.0', category: 'Infrastructure', description: 'Container runtime' },
  { name: 'Docker Compose', version: '2.x', license: 'Apache-2.0', category: 'Infrastructure', description: 'Multi-container orchestration' },
  { name: 'Azure App Service', version: 'N/A', license: 'Proprietary', category: 'Infrastructure', description: 'Cloud hosting platform' },
  { name: 'Azure Database for PostgreSQL', version: '16', license: 'Proprietary', category: 'Infrastructure', description: 'Managed PostgreSQL service' },

  // Dev Tooling
  { name: 'ESLint', version: '9.x', license: 'MIT', category: 'Dev Tooling', description: 'JavaScript/TypeScript linter' },
  { name: '@vitejs/plugin-react', version: '5.x', license: 'MIT', category: 'Dev Tooling', description: 'Vite React plugin with Fast Refresh' },
  { name: 'typescript-eslint', version: '8.x', license: 'MIT', category: 'Dev Tooling', description: 'TypeScript ESLint integration' },
  { name: 'Prettier', version: '3.x', license: 'MIT', category: 'Dev Tooling', description: 'Code formatter' },
  { name: 'pyenv', version: 'N/A', license: 'MIT', category: 'Dev Tooling', description: 'Python version management' },
  { name: 'pip', version: '24.x', license: 'MIT', category: 'Dev Tooling', description: 'Python package installer' },
];

export const sbomCategories = ['All', 'Frontend', 'Backend', 'Database', 'Infrastructure', 'Dev Tooling'] as const;
