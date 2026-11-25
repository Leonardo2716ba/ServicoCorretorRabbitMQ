# Worker

Consumidor Python que transforma submissões em resultados. Código em `worker/`.

## Módulos

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `config.py` | Todas as variáveis de ambiente | `os`, `python-dotenv` |
| `messaging.py` | Conexão, declaração de filas, consumo e publicação no RabbitMQ | `pika` |
| `sandbox.py` | Cria o container, entrega a submissão, espera, classifica o veredito e remove | `docker` |
| `grading.py` | Regra de correção: roda o sandbox, interpreta o relatório e monta o resultado | `sandbox` |
| `worker.py` | Ponto de entrada: liga a mensageria à correção e decide `ack`/`nack` | os demais |

Dependências em uma só direção: `worker` → `grading` → `sandbox` → `config`, e `worker` → `messaging` → `config`. Só `sandbox.py` importa `docker` e só `messaging.py` importa `pika`.

## Ciclo de vida de uma mensagem

1. `messaging.consume_requests` entrega a mensagem a `worker.handle_correction_request`.
2. O corpo é lido como JSON e o `task_delivered_id` é extraído.
3. `grading.grade_submission` executa o sandbox e monta o resultado.
4. `messaging.publish_result` publica em `grading.results` (persistente, com `correlation_id` igual ao `task_delivered_id`).
5. O worker confirma a mensagem original.

| Situação | Ação |
|---|---|
| JSON inválido, sem `task_delivered_id` ou que não seja um objeto | `nack` **sem** requeue (descartada) |
| Exceção ao processar ou publicar (infraestrutura) | `nack` **com** requeue (volta para a fila) |
| Qualquer veredito de execução, inclusive erro do aluno | Resultado publicado e `ack` |

Um erro do código do aluno **não** é falha do worker: vira um veredito no resultado.

## Escalabilidade

- Cada worker usa uma conexão bloqueante (`BlockingConnection`) e processa **uma mensagem por vez**. Para paralelizar, suba mais réplicas.
- `RABBITMQ_PREFETCH_COUNT` controla quantas mensagens o worker puxa de uma vez. Com várias réplicas, `1` distribui melhor a carga; valores maiores deixam mensagens reservadas em um worker enquanto outros ficam ociosos.
- O worker precisa acessar o socket do Docker do host (para criar os sandboxes).

## Execução local

```bash
cd worker
pip install -r requirements.txt
export RABBITMQ_URL=amqp://guest:guest@localhost:5672
export RABBITMQ_QUEUE_GRADING_REQUESTS=grading.requests
export RABBITMQ_QUEUE_GRADING_RESULTS=grading.results
python worker.py
```

Na inicialização o worker verifica se o Docker está acessível e falha imediatamente se não estiver.