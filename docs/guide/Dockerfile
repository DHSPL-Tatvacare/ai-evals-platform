FROM node:20-alpine

WORKDIR /app

COPY package.json ./
COPY package-lock.json ./
RUN npm ci

COPY . .

ENV GUIDE_SKIP_SYNC=true

RUN npm run build

EXPOSE 5174

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5174"]
