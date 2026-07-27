FROM node:20-bookworm-slim

ENV NODE_ENV=production
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_SKIP_DOWNLOAD=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY whatsapp-web-gateway/package.json whatsapp-web-gateway/package-lock.json ./
RUN npm ci --omit=dev --omit=optional

COPY whatsapp-web-gateway/src ./src

EXPOSE 3020
CMD ["node", "src/server.js"]
