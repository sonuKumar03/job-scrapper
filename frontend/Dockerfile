FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS development
WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . ./
EXPOSE 3000
CMD ["npm", "run", "dev"]
