# ServicoCorretorRabbitMQ

Ambiente mínimo com **3 componentes**, seguindo o fluxo do seu TCC, mas sem a etapa de
banco de dados de questões (MongoDB entra depois):

- **rabbitmq** — broker de mensagens (fila `submissoes`)
- **flask-api** — recebe submissões (`POST /submissoes`) e publica na fila; consulta
  resultados (`GET /submissoes/<id>`)
- **corretor** — consome a fila com ACK manual, executa o código em um container
  Docker isolado (limite de memória/CPU, sem rede) e grava o resultado

## Como rodar

```bash
cd workqueue-test
docker compose up --build
```

Isso sobe RabbitMQ (com painel em http://localhost:15672, usuário/senha
`guest`/`guest`), a API em `http://localhost:5000` e um corretor.

Para simular múltiplos corretores concorrentes (como no diagrama do TCC):

```bash
docker compose up --build --scale corretor=3
docker compose exec flask-api sh -c "rm -f /data/results/*.json"
```

## Testando o fluxo

**1. Enviar uma submissão:**

```bash
curl -X POST http://localhost:5000/submissoes \
  -H "Content-Type: application/json" \
  -d '{
    "codigo": "import random\n
    n = 1000\n
    vetor = list(range(n, 0, -1))\n
    trocas = 0\n
    for i in range(len(vetor)):
    \n    for j in range(len(vetor) - i - 1):
    \n        if vetor[j] > vetor[j + 1]:
    \n            vetor[j], vetor[j + 1] = vetor[j + 1], vetor[j]
    \n            trocas += 1\n
    print(f\"ordenado n={n} trocas={trocas} ok={vetor == sorted(vetor)}\")",
    "id_questao": "q1",
    "id_aluno": "aluno123"
  }'
```

Depois de `TIMEOUT_SEGUNDOS` (padrão 5s), o resultado deve vir com
`"veredito": "tempo_limite_excedido"`.

## Observações técnicas

- O corretor monta `/var/run/docker.sock` do host, então ele cria containers
  **irmãos** (sibling containers) via `docker-py`, sem precisar de
  Docker-in-Docker.
- Ele usa `python:3.11-slim` para rodar o código do aluno — na primeira
  execução o Docker vai baixar essa imagem, o que pode levar alguns segundos.
- Limites configuráveis via variáveis de ambiente no `docker-compose.yml`:
  `TIMEOUT_SEGUNDOS`, `MEM_LIMIT`, `CPU_QUOTA`.
- Consumo com ACK manual (`prefetch_count=1`): se o corretor cair no meio do
  processamento, a mensagem não é confirmada e volta para a fila — igual ao
  que está descrito na Seção 3.1 do seu texto.