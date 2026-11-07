import amqp from 'amqplib';
import { dataObject } from './validation';
import { stats } from './stats';

const RABBITMQ_URL = process.env.RABBITMQ_URL ?? 'amqp://localhost';

export const RABBITMQ_QUEUE_GRADING_REQUESTS = process.env.RABBITMQ_QUEUE_GRADING_REQUESTS ?? 'grading.requests';
export const RABBITMQ_QUEUE_GRADING_RESULTS = process.env.RABBITMQ_QUEUE_GRADING_RESULTS ?? 'grading.results';
const OPCODERS_SERVER = process.env.OPCODERS_SERVER ?? 'http://localhost:3005/api/opcoders-sim';

let channel: amqp.Channel | null = null;
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));


export const connectRabbitMQ = async (): Promise<void> => {
  const connection = await amqp.connect(RABBITMQ_URL);
  channel = await connection.createChannel();
  /** Criando filas*/
  await channel.assertQueue(RABBITMQ_QUEUE_GRADING_REQUESTS, { durable: true });
  await channel.assertQueue(RABBITMQ_QUEUE_GRADING_RESULTS, { durable: true });
  console.log('Connected to RabbitMQ');
};

export async function checkResultQueue(): Promise<void> {
  const connection = await amqp.connect(RABBITMQ_URL);
  const consumerChannel = await connection.createChannel();

  await consumerChannel.assertQueue(RABBITMQ_QUEUE_GRADING_RESULTS, { durable: true });
  consumerChannel.prefetch(16);

  await consumerChannel.consume(
    RABBITMQ_QUEUE_GRADING_RESULTS,
    async (message) => {
      if (message === null) {
        console.log('Consumidor cancelado pelo RabbitMQ.');
        return;
      }
      try {
        const conteudo = message.content.toString();
        const resultado = JSON.parse(conteudo);

          //const respostaExterna = await fetch(OPCODERS_SERVER,
          const respostaExterna = await fetch("http://192.168.31.70:3000/api/v1/ultima", {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: conteudo,
        });

        if (!respostaExterna.ok)
          throw new Error(`Servidor respondeu com status ${respostaExterna.status}`);
        
       
        consumerChannel.ack(message);
        const now = Date.now();
        
        stats.completed++;
        stats.lastCompletedAt = now;

        stats.results.push({
          task_delivered_id: resultado.task_delivered_id,
          execution_status: resultado.execution_status,
          container_runtime_seconds: resultado.container_runtime_seconds,
          question_score: resultado.question_score,
          completedAt: now,
        });
      } catch (error) {
        console.error('Erro ao processar resultado:', error);
        await sleep(1000); // evita hot loop de requeue
        consumerChannel.nack(message, false, true);
      }
    },
    { noAck: false },
  );
}

export const publishMessage = (queue: string, object: dataObject): boolean => {
  if (!channel) {
    console.error('Canal do RabbitMQ não está disponível.');
    return false;
  }
  try {
    const content = Buffer.from(JSON.stringify(object));
    const sent = channel.sendToQueue(queue, content, { persistent: true });
    return sent;
  } catch (error) {
    console.error('Erro ao publicar mensagem:', error);
    return false;
  }
};