FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg + Playwright Chromium runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    libxfixes3 libx11-xcb1 libxcb1 libxext6 libx11-6 \
    libdbus-1-3 libexpat1 libglib2.0-0 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

RUN mkdir -p /app/uploads

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8721

ENTRYPOINT ["/entrypoint.sh"]
