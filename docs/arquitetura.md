# Arquitetura

## Componentes

| Componente | Tecnologia | Responsabilidade |
|---|---|---|
| API | Node.js, Express, amqplib | Valida submissões, publica em `grading.requests`, consome `grading.results` e repassa o resultado ao opCoders |
| Fila | RabbitMQ | Desacopla a API dos workers e guarda as mensagens até serem processadas |
| Worker | Python, pika, docker SDK | Consome submissões, executa cada uma em um sandbox e publica o resultado |
| Sandbox | Docker (`runner-sandbox`) | Executa o código do aluno isolado, com limites de memória, CPU, processos e sem rede |
| opCoders | Servidor externo | Recebe o resultado final da correção |

## Fluxo de uma submissão

1. O cliente envia `POST /api/v1/grade` com a submissão.
2. A API valida o payload. Se for válido, publica em `grading.requests` e responde `202`.
3. Um worker consome a mensagem, cria um container novo a partir de `runner-sandbox`, entrega o `submission.json` e espera o término.
4. O worker classifica o resultado (veredito), monta o relatório e publica em `grading.results`. Depois confirma (`ack`) a mensagem original.
5. A API consome `grading.results`, envia o resultado por `POST` ao servidor do opCoders e só então confirma a mensagem.

## Filas

| Fila | Produtor | Consumidor | Conteúdo |
|---|---|---|---|
| `grading.requests` | API | Workers | Submissão a corrigir |
| `grading.results` | Workers | API | Submissão corrigida, com veredito e relatório |

Os nomes vêm de variáveis de ambiente (ver [configuracao.md](configuracao.md)). As duas filas são duráveis e as mensagens são persistentes.

## Garantias de entrega

- O `ack` é manual nos dois consumidores: a mensagem só sai da fila depois de processada.
- Falhas de infraestrutura devolvem a mensagem à fila (`nack` com requeue). A entrega é, portanto, **pelo menos uma vez**, e uma submissão pode ser processada mais de uma vez. Quem consome o resultado deve tratar `task_delivered_id` como chave de idempotência.
- Mensagens malformadas no worker são descartadas (`nack` sem requeue), porque nunca vão funcionar.

## Decisões de projeto

- **Um container por submissão.** Cada execução usa um container novo, removido ao final, para que uma submissão nunca enxergue o estado de outra.
- **Paralelismo por réplicas de worker.** Cada worker processa uma mensagem por vez; para corrigir mais submissões ao mesmo tempo, aumente o número de workers (ver [operacao.md](operacao.md)).
- **Worker agnóstico ao relatório.** A lógica de correção fica dentro da imagem do sandbox; o worker só interpreta o relatório JSON (ver [sandbox.md](sandbox.md)).