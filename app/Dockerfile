# ---- build ----
FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY client ./client
COPY public ./public
COPY src ./src
RUN npm run build

# ---- run: production deps only, non-root user ----
FROM node:24-alpine
ENV NODE_ENV=production
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
COPY views ./views
COPY --from=build /app/public ./public
USER node
EXPOSE 8080
CMD ["node", "dist/main.js"]
