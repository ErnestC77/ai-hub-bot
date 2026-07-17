# frontend-next/Dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* vars are inlined into the client bundle at `next build` time, not read at
# container runtime -- Render only injects envVars into the running container, so they must
# be explicitly re-declared as build ARGs to reach this build stage.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SUPPORT_USERNAME
ENV NEXT_PUBLIC_SUPPORT_USERNAME=$NEXT_PUBLIC_SUPPORT_USERNAME
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
