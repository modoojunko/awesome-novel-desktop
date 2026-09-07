# ── Build stage：tsc 类型检查 + vite build ──
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# 品牌单源（brand-name-single-source）：brand.json 在仓库根、不在本构建上下文，
# 由 compose additional_contexts 以命名上下文 brand 注入（vite 构建期读取）
COPY --from=brand brand.json /brand/brand.json
RUN npm run build

# ── Serve stage：nginx 托管 dist，/api 代理到 client-backend ──
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
