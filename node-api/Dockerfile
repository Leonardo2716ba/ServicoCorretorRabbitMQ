# ============================================================
# Estagio 1: build
# Compila o TypeScript para JavaScript. Tem todas as ferramentas
# de desenvolvimento, mas e descartado no final: so o resultado
# (dist/) e aproveitado pelo estagio seguinte.
# ============================================================
FROM node:22-alpine AS build
WORKDIR /app

COPY package*.json ./

# Instala TODAS as dependencias, inclusive as de desenvolvimento
RUN npm ci

COPY tsconfig.json ./
COPY src ./src

RUN npm run build

# ============================================================
# Estagio 2: runtime
# Imagem final, a que realmente roda em producao. Contem apenas
# as dependencias de execucao e o JavaScript ja compilado, sem
# compilador nem codigo .ts.
# ============================================================
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./

# Instala apenas as dependencias de producao (express, amqplib)
# e limpa o cache do npm para deixar a imagem menor
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /app/dist ./dist

USER node

EXPOSE 3000

CMD ["node", "dist/api.js"]