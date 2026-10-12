import express, { Request, Response } from 'express';
import amqp from 'amqplib';

const PORT = Number(process.env.PORT ?? 3000);
const RABBITMQ_URL = process.env.RABBITMQ_URL ?? 'amqp://localhost';

const RABBITMQ_QUEUE_GRADING_REQUESTS =  process.env.RABBITMQ_QUEUE_GRADING_REQUESTS ?? 'grading.requests';
const RABBITMQ_QUEUE_GRADING_RESULTS =  process.env.RABBITMQ_QUEUE_GRADING_RESULTS ?? 'grading.results';


const server = express();
server.use(express.json());

let channel: amqp.Channel | null = null;

interface dataObject {
  task_delivered_id: number; 
  question_score: number;
  is_pending: boolean;
  code_sent: string;
  correction_strategy_id: number;
  test_cases: any[];   
}

function isNull(value: unknown): boolean{
    if(value == null)
        return true;
    return false;
}

function dataValidation(object: dataObject) {
  const errors: string[] = [];

  const {
    task_delivered_id,
    question_score,
    is_pending,
    code_sent,
    correction_strategy_id,
    test_cases,
  } = object;

  if (isNull(task_delivered_id))
    errors.push("O campo obrigatório 'task_delivered_id' ausente");
  else if (typeof task_delivered_id !== 'number')
    errors.push("O campo 'task_delivered_id' deve ser um número.");

  if (isNull(correction_strategy_id))
    errors.push("O campo obrigatório 'correction_strategy_id' ausente");
  else if (typeof correction_strategy_id !== 'number')
    errors.push("O campo 'correction_strategy_id' deve ser um número.");

  if (isNull(question_score))
    errors.push("O campo obrigatório 'question_score' ausente");
  else if (typeof question_score !== 'number')
    errors.push("O campo 'question_score' deve ser um número.");

  if (isNull(is_pending))
    errors.push("O campo obrigatório 'is_pending' ausente");
  else if (typeof is_pending !== 'boolean')
    errors.push("O campo 'is_pending' deve ser um booleano.");

  if (isNull(code_sent))
    errors.push("O campo obrigatório 'code_sent' ausente");
  else if (typeof code_sent !== 'string')
    errors.push("O campo 'code_sent' deve ser uma string.");

  if (isNull(test_cases))
    errors.push("O campo obrigatório 'test_cases' ausente");
  else if (!Array.isArray(test_cases))
    errors.push("O campo 'test_cases' deve ser uma lista (array).");
  else if (test_cases.length < 1)
    errors.push("O campo 'test_cases' deve conter no mínimo um caso de teste.");

  if (errors.length > 0)
    return { success: false, errors };

  return {
    success: true,
    data: object as dataObject,
    errors
  };
}

const connectRabbitMQ = async (): Promise<void> => {
    const connection = await amqp.connect(RABBITMQ_URL);
    channel = await connection.createChannel();
    /** Criando filas*/
    await channel.assertQueue(RABBITMQ_QUEUE_GRADING_REQUESTS, { durable: true });
    await channel.assertQueue(RABBITMQ_QUEUE_GRADING_RESULTS, { durable: true });
    console.log('Connected to RabbitMQ');
};


const publishMessage = (queue: string, object: dataObject): boolean => {
    if (!channel) {
        console.error('Canal do RabbitMQ não está disponível.');
        return false;
    }

    try {
        const content = Buffer.from(JSON.stringify(object));
        const sent = channel.sendToQueue(queue, content, { persistent: true });
        console.log(`Message sent to ${queue}:`, object);
        return sent;
    } catch (error) {
        console.error('Erro ao publicar mensagem:', error);
        return false;
    }
};


server.get('/', (request: Request, response: Response) => {
    return response.status(200).json({message: "O servidor node js está funcionando"})
});


server.post('/api/v1/grade',(request: Request, response: Response) => {
    const data: dataObject = request.body as dataObject
    const validation_result = dataValidation(data)
    
    if (!validation_result.success)
        return response.status(400).json(validation_result.errors) 

    if (publishMessage(RABBITMQ_QUEUE_GRADING_REQUESTS, data))
    return response.status(202).json({ message: 'Submissão enviada para correção.' });

    return response.status(503).json({ message: 'Não foi possível enfileirar a submissão.' });
});

connectRabbitMQ()
    .then(() => server.listen(PORT, () => console.log(`Servidor na porta ${PORT}`)))
    .catch((error) => {
        console.error('Erro ao conectar o RabbitMQ', error);
        process.exit(1);
    });