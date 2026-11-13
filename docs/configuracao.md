# Configuração

Todas as variáveis ficam em um arquivo `.env` na raiz (modelo em `.env.example`). O `.env` não deve ser versionado.

## Worker (`worker/config.py`)

| Variável | Padrão | Descrição |
|---|---|---|
| `RABBITMQ_URL` | — (obrigatória) | URL de conexão, por exemplo `amqp://guest:guest@rabbitmq:5672` |
| `RABBITMQ_QUEUE_GRADING_REQUESTS` | — (obrigatória) | Fila de submissões |
| `RABBITMQ_QUEUE_GRADING_RESULTS` | — (obrigatória) | Fila de resultados |
| `RABBITMQ_PREFETCH_COUNT` | `2` | Mensagens puxadas por vez |
| `SANDBOX_IMAGE` | `runner-sandbox` | Imagem do sandbox |
| `SANDBOX_DEFAULT_MEM_LIMIT` | `32m` | Memória do sandbox |
| `SANDBOX_MAX_TIME_LIMIT_SECONDS` | `2` | Tempo máximo que o worker espera o container |
| `SANDBOX_CPU_QUOTA` | `90000` | Cota de CPU (período fixo de 100000) |
| `SANDBOX_PIDS_LIMIT` | `64` | Máximo de processos no sandbox |
| `DEFAULT_TEST_CASE_TIME_LIMIT_SECONDS` | `2` | Tempo por caso de teste quando a submissão não informa |
| `RESULTS_DIR` | `/data/results` | Não é usado pelos módulos atuais |

O worker falha na inicialização, com o nome da variável, se alguma obrigatória estiver ausente.

## API Node.js

| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | `3000` | Porta HTTP |
| `RABBITMQ_URL` | `amqp://localhost` | URL de conexão |
| `RABBITMQ_QUEUE_GRADING_REQUESTS` | `grading.requests` | Fila de submissões |
| `RABBITMQ_QUEUE_GRADING_RESULTS` | `grading.results` | Fila de resultados |
| `OPCODERS_SERVER` | `http://localhost:3005/api/opcoders-sim` | Endpoint que recebe os resultados |

## Compose e testes

| Variável | Descrição |
|---|---|
| `EXPRESS_API_HOST`, `EXPRESS_API_PORT` | Endereço da API, usado pelo compose e pelos testes. **A confirmar** |
| `WORKER_MEM_LIMIT` | Limite de memória do container do worker (não é o do sandbox). **A confirmar** |

## Cuidados

- Dentro do Docker use o **nome do serviço** (`rabbitmq`) no `RABBITMQ_URL`, nunca o IP da máquina: o IP da rede local muda e causa `EHOSTUNREACH`.
- O IP da máquina só aparece em quem acessa de fora, como o `API_URL` do k6 em outro computador.