FROM mcr.microsoft.com/playwright:v1.55.0-noble
WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev
COPY src ./src
ENV NODE_ENV=production
ENV PORT=10000
ENV TERABOX_PROFILE_DIR=/var/data/terabox-profile
ENV TERABOX_STATE_FILE=/var/data/terabox-state.json
ENV TERABOX_TMP_DIR=/var/data/tmp
ENV TERABOX_DOWNLOAD_DIR=/var/data/downloads
EXPOSE 10000
CMD ["node","src/server.js"]

