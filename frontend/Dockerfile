# syntax=docker/dockerfile:1
# Build
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm set -eu; \
    for attempt in 1 2 3; do \
        rm -rf node_modules; \
        if npm ci --include=dev --no-audit --no-fund && test -x node_modules/.bin/tsc; then \
            exit 0; \
        fi; \
        echo "npm ci attempt ${attempt} failed or did not install tsc"; \
        sleep $((attempt * 5)); \
    done; \
    exit 1
COPY . .
RUN npm run build

# Serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
