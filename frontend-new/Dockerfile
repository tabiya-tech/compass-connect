FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 300000

COPY . .

# CRA builds are memory hungry
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN yarn build

## Final image: static files served by nginx, runtime configuration generated on start

FROM nginxinc/nginx-unprivileged:alpine

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown

COPY --from=builder /app/build /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 docker/40-generate-env-js.sh /docker-entrypoint.d/40-generate-env-js.sh

USER root
# jq parses FRONTEND_SEO at start-up; index.html is regenerated from the untouched template on every start
RUN apk add --no-cache jq \
    && mv /usr/share/nginx/html/index.html /usr/share/nginx/html/index.template.html \
    && touch /usr/share/nginx/html/index.html \
    && chown nginx:nginx /usr/share/nginx/html/index.html \
    && mkdir -p /usr/share/nginx/html/data \
    && printf '{"date":"%s","sha":"%s"}\n' "$BUILD_DATE" "$GIT_SHA" > /usr/share/nginx/html/data/version.json \
    && chown -R nginx:nginx /usr/share/nginx/html/data
USER nginx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
