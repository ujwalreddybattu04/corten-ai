FROM node:22-alpine AS base

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Development
FROM base AS dev
CMD ["npm", "run", "dev"]

# Production build
FROM base AS builder
# Keep browser requests on the frontend origin. BACKEND_URL is set at runtime.
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build \
    && npm prune --omit=dev --ignore-scripts

FROM node:22-alpine AS production
WORKDIR /app
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js

# Cloud Run injects PORT env var; Next.js defaults to 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
EXPOSE ${PORT}

CMD ["sh", "-c", "exec node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port \"${PORT:-3000}\""]
