# Sandbox

Container que executa o código do aluno. A imagem fica em `runner-sandbox/` e o ciclo de vida é controlado por `worker/sandbox.py`.

## Imagem

| Arquivo | Função |
|---|---|
| `Dockerfile` | Constrói a imagem `runner-sandbox` |
| `corrigeQuestao.py` | Ponto de entrada: lê o `submission.json`, executa os casos de teste e imprime o relatório |
| `biblioteca.py` | Funções de apoio usadas pelo corretor |
| `requirements.txt` | Dependências Python da imagem |

```bash
docker build -t runner-sandbox ./runner-sandbox
```

## Como o worker executa

1. Cria o container com `python corrigeQuestao.py submission.json <tempo_por_caso>`, diretório de trabalho `/app`.
2. Copia o `submission.json` para `/app` (arquivo `tar` enviado ao container).
3. Inicia o container e espera até `SANDBOX_MAX_TIME_LIMIT_SECONDS`.
4. Lê os logs e o estado do container, define o veredito e remove o container (`force=True`), mesmo em caso de erro.

`submission.json` contém: `task_delivered_id`, `correction_strategy_id`, `question_score`, `code_sent` e `test_cases`.

## Limites de recursos

| Limite | Valor padrão | Como muda |
|---|---|---|
| Memória | `32m`, sem swap | `SANDBOX_DEFAULT_MEM_LIMIT` ou `sandbox_mem_limit` na submissão |
| CPU | 90% de um core (`cpu_quota=90000` / `cpu_period=100000`) | `SANDBOX_CPU_QUOTA` |
| Processos | 64 | `SANDBOX_PIDS_LIMIT` |
| Rede | desabilitada | fixo |
| Tempo do container | 2 s | `SANDBOX_MAX_TIME_LIMIT_SECONDS` |
| Tempo por caso de teste | 2 s | `DEFAULT_TEST_CASE_TIME_LIMIT_SECONDS` ou `test_case_time_limit_seconds` na submissão |

O tempo do container conta a partir do `start`, portanto inclui a inicialização do Python.

## Vereditos (`execution_status`)

Avaliados nesta ordem:

| Veredito | Quando |
|---|---|
| `tempo_limite_container_excedido` | O container não terminou dentro do limite; é encerrado (`kill`) |
| `limite_memoria_excedido` | O container foi morto por falta de memória (`OOMKilled`) |
| `concluida` | O container terminou com código de saída `0` |
| `limite_processos_excedido` | Saída diferente de `0` com erro de criação de processo ou thread nos logs |
| `erro_execucao` | Qualquer outra saída diferente de `0` |
| `erro_infraestrutura` | Falha ao criar, iniciar ou consultar o container |

## Relatório

O worker interpreta a saída do container (últimas 200 linhas, no máximo 20.000 caracteres) como um objeto JSON. Quando o veredito é `concluida`, a nota vem do campo `NotaFinal`. Se a saída não for um objeto JSON, o relatório fica como `{"raw_output": "<saída>"}`.

## Limitações conhecidas

- A saída inteira é lida como um único JSON. Qualquer texto extra no stdout/stderr do container impede a leitura do relatório.
- Se o relatório passar de 20.000 caracteres, ele é truncado e deixa de ser JSON válido.
- Se `NotaFinal` faltar em uma execução `concluida`, a nota vira `0.0` sem aviso.
- Só há uma linguagem (Python) e nenhuma etapa de compilação.