# TDMS frontend container image.
#
# Multi-stage: dependencies -> build -> production runtime.
# Only the standalone server output and static assets reach the final image, so
# no development file or source tree is shipped.

# ---------------------------------------------------------------- dependencies
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ----------------------------------------------------------------------- build
FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_ values are embedded at build time, so they are supplied as build
# arguments. Never pass a secret here: everything NEXT_PUBLIC_ ends up in the
# browser bundle.
ARG NEXT_PUBLIC_APP_NAME=TDMS
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_TDMS_DATA_MODE=mock
ARG NEXT_PUBLIC_TDMS_AUTH_MODE=mock
ARG NEXT_PUBLIC_TDMS_DEV_TOOLS=false
ENV NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_TDMS_DATA_MODE=$NEXT_PUBLIC_TDMS_DATA_MODE \
    NEXT_PUBLIC_TDMS_AUTH_MODE=$NEXT_PUBLIC_TDMS_AUTH_MODE \
    NEXT_PUBLIC_TDMS_DEV_TOOLS=$NEXT_PUBLIC_TDMS_DEV_TOOLS \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ------------------------------------------------------------------- runtime
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
