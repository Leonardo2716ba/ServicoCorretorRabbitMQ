"""Ponto de entrada: liga a mensageria a regra de correcao."""
import json

import messaging
import sandbox
from grading import grade_submission


def handle_correction_request(channel, method, properties, body):
    # mensagem malformada nunca vai funcionar: descarta em vez de reenfileirar
    try:
        payload = json.loads(body)
        task_delivered_id = payload["task_delivered_id"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f" [!] Mensagem invalida descartada: {exc}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    print(f" [x] Processando task_delivered {task_delivered_id}")

    try:
        resultado = grade_submission(payload)
        messaging.publish_result(channel, task_delivered_id, resultado)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        # erro de infraestrutura: devolve a mensagem para a fila
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        print(f" [!] Falha ao processar {task_delivered_id}: {exc}")


def main():
    sandbox.get_docker_client()  # falha logo na inicializacao se o Docker nao estiver acessivel
    connection = messaging.connect()
    channel = connection.channel()
    messaging.declare_queues(channel)
    messaging.consume_requests(channel, handle_correction_request)

    print(" [*] Corretor aguardando submissoes. CTRL+C para sair.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()