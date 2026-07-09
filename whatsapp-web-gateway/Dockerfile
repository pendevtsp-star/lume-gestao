FROM node:20-bookworm-slim

ENV NODE_ENV=production
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_SKIP_DOWNLOAD=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY whatsapp-web-gateway/package.json ./package.json
RUN npm install --omit=dev

COPY whatsapp-web-gateway/src ./src

EXPOSE 3020
CMD ["node", "src/server.js"]
