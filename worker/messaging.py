"""Camada de mensageria: tudo que fala com o RabbitMQ (pika) fica aqui."""
import json

import pika

import config


def connect() -> pika.BlockingConnection:
    params = pika.URLParameters(config.RABBITMQ_URL)
    params.heartbeat = config.RABBITMQ_HEARTBEAT_SECONDS
    params.blocked_connection_timeout = config.RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS
    return pika.BlockingConnection(params)


def declare_queues(channel) -> None:
    # se as filas ja existem, o RabbitMQ ignora
    channel.queue_declare(queue=config.RABBITMQ_QUEUE_GRADING_REQUESTS, durable=True)
    channel.queue_declare(queue=config.RABBITMQ_QUEUE_GRADING_RESULTS, durable=True)


def consume_requests(channel, callback) -> None:
    # ACK manual: a mensagem so sai da fila quando o callback confirma
    channel.basic_qos(prefetch_count=config.RABBITMQ_PREFETCH_COUNT)
    channel.basic_consume(
        queue=config.RABBITMQ_QUEUE_GRADING_REQUESTS,
        on_message_callback=callback,
    )


def publish_result(channel, task_delivered_id, resultado: dict) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=config.RABBITMQ_QUEUE_GRADING_RESULTS,
        body=json.dumps(resultado),
        properties=pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            correlation_id=str(task_delivered_id),
        ),
        mandatory=True,
    )