# Operação

## Subir o sistema

```bash
cp .env.example .env
docker build -t runner-sandbox ./runner-sandbox
docker compose up --build -d
```

**A confirmar:** nomes dos serviços e arquivos do compose.

## Escalar workers

Cada worker corrige uma submissão por vez. Para aumentar o paralelismo:

```bash
docker compose up -d --scale worker=8
```

Escolha o número de workers considerando a CPU do host: cada sandbox pode usar até 90% de um core, e o daemon do Docker também fica sob carga ao criar e remover containers.

## Filas do RabbitMQ

Listar as filas e a quantidade de mensagens:

```bash
docker exec opjudge-rabbitmq-1 rabbitmqctl list_queues name messages
```

Apagar as mensagens de uma fila:

```bash
docker exec opjudge-rabbitmq-1 rabbitmqctl purge_queue grading.requests
docker exec opjudge-rabbitmq-1 rabbitmqctl purge_queue grading.results
```

Use `docker exec` sem `-it` em scripts. Mensagens já entregues a um consumidor e ainda não confirmadas não são apagadas pelo `purge_queue`.

## Rede

- **Entre containers**, use o nome do serviço (`rabbitmq`), nunca o IP da máquina.
- **De outro computador**, a porta da API precisa estar publicada (`ports: "3000:3000"`) e acessível pela rede local: `http://<IP-da-máquina>:3000`.
- Prefira cabo e reserve o IP da máquina no roteador (DHCP estático), porque o IP dinâmico muda.
- Se houver Wi-Fi e cabo ativos na mesma sub-rede, desligue um deles durante testes de carga.

## Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| API reinicia com `EHOSTUNREACH` ao conectar no RabbitMQ | `RABBITMQ_URL` aponta para um IP que mudou | Use o nome do serviço na rede do Docker |
| Worker cai com `ModuleNotFoundError` | O `Dockerfile` do worker não copia todos os módulos | Use `COPY *.py ./` e reconstrua a imagem |
| Worker cai com `Variavel de ambiente obrigatoria nao definida` | Falta variável no ambiente do container | Confira o `.env` e o compose |
| Muitos `tempo_limite_container_excedido` com vários workers | O boot do Python sob carga estoura o limite do container | Aumente `SANDBOX_MAX_TIME_LIMIT_SECONDS` |
| `limite_memoria_excedido` em submissões simples | Limite de memória baixo para o código | Aumente `SANDBOX_DEFAULT_MEM_LIMIT` ou envie `sandbox_mem_limit` |
| Logs do worker aparecem com atraso | Saída do Python em buffer | Defina `PYTHONUNBUFFERED=1` no `Dockerfile` |
| Sobraram containers de sandbox | Worker encerrado no meio de uma execução | `docker ps -a` e `docker rm -f` nos containers `runner-sandbox` |