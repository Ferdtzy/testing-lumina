# ── Frontend Dockerfile (Next.js) ────────────────────────────────────────────
FROM node:22-alpine

# Set working directory
WORKDIR /app

# Copy package files first for better layer caching
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the application
COPY . .

# Expose Next.js dev server port
EXPOSE 3000

# Default command: run Next.js dev server
CMD ["npm", "run", "dev"]