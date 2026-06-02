# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 1b: Build the docs (Zudoku, basePath /docs → dist/docs) ────────────
FROM node:20-slim AS docs

WORKDIR /docs

COPY apidocs/package.json apidocs/package-lock.json ./
RUN npm ci

COPY apidocs/ ./
RUN npm run build

# ── Stage 2: Serve ───────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Custom config: serve SPA + docs + proxy /api to backend container
COPY nginx.prod.conf /etc/nginx/conf.d/app.conf

# Copy built React app
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy built docs site, served at /docs
COPY --from=docs /docs/dist/docs /usr/share/nginx/html/docs

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
