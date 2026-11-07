import express, { Request, Response } from 'express';
import { dataObject, dataValidation } from './validation';
import {
  connectRabbitMQ,
  checkResultQueue,
  publishMessage,
  RABBITMQ_QUEUE_GRADING_REQUESTS,
} from './rabbitmq';
import { stats, resetStats } from './stats';

const PORT = Number(process.env.PORT ?? 3000);

const server = express();
server.use(express.json());

let corrigidas: any = {};

server.get('/', (request: Request, response: Response) => {
  return response.status(200).json({ message: 'O servidor node js está funcionando' });
});

server.get('/api/v1/stats', (_req, res) => res.json(stats));

server.post('/api/v1/stats/reset', (_req, res) => {
  resetStats();
  res.status(204).end();
});

server.get('/api/v1/ultima', (_req, res) => res.json(corrigidas));

server.post('/api/v1/ultima', (request: Request, response: Response) => {
  // CORREÇÃO: request.body é uma propriedade, não uma função
  corrigidas = request.body; 
  
  // Retorna o status 201 (Created) junto com o dado salvo
  return response.status(201).json({ status: "sucesso", dados: corrigidas });
});


server.post('/api/v1/grade', (request: Request, response: Response) => {
  const data: dataObject = request.body as dataObject;
  const validation_result = dataValidation(data);

  if (!validation_result.success)
    return response.status(400).json(validation_result.errors);

  // registra antes de publicar, para o makespan incluir o tempo do primeiro envio
  const antes = stats.firstSubmitAt;
  stats.firstSubmitAt ??= Date.now();

  if (publishMessage(RABBITMQ_QUEUE_GRADING_REQUESTS, data)) {
    stats.submitted++;
    return response.status(202).json({ message: 'Submissão enviada para correção.' });
  }

  // falhou ao publicar: desfaz o registro
  stats.firstSubmitAt = antes;
  return response.status(503).json({ message: 'Não foi possível enfileirar a submissão.' });
});

connectRabbitMQ()
  .then(() => {
    server.listen(PORT, () => console.log(`Servidor na porta ${PORT}`));
    return checkResultQueue();
  })
  .catch((error) => {
    console.error('Erro ao conectar o RabbitMQ', error);
    process.exit(1);
  });