FROM node:20-alpine AS base
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=base /app/.next/standalone ./
COPY --from=base /app/.next/static ./.next/static
COPY --from=base /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
