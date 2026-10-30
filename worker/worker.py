import os
import io
import json
import time
import tarfile

import requests

import pika
import docker

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "runner-sandbox")

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_QUEUE_GRADING_REQUESTS = os.environ.get("RABBITMQ_QUEUE_GRADING_REQUESTS", "grading.requests")
RABBITMQ_QUEUE_GRADING_RESULTS = os.environ.get("RABBITMQ_QUEUE_GRADING_RESULTS", "grading.results")

RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")

TIMEOUT_SEGUNDOS = int(os.environ.get("TIMEOUT_SEGUNDOS", "2"))
MEM_LIMIT = os.environ.get("MEM_LIMIT", "64m")
CPU_QUOTA = int(os.environ.get("CPU_QUOTA", "50000"))  # cpu_period padrao = 100000 # Equivale a 100%

os.makedirs(RESULTS_DIR, exist_ok=True)

docker_client = docker.from_env()

def extrair_nota(saida: str):
    # procura de tras para frente a ultima linha que seja o JSON do resultado
    for linha in reversed(saida.strip().splitlines()):
        try:
            dados = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(dados, dict) and "NotaFinal" in dados:
            return float(dados["NotaFinal"])
    return None

def _caminho_resultado(task_delivered_id: int) -> str:
    return os.path.join(RESULTS_DIR, f"{task_delivered_id}.json")


def atualizar_resultado(task_delivered_id: int, **campos):
    caminho = _caminho_resultado(task_delivered_id)
    resultado = {}
    if os.path.exists(caminho):
        with open(caminho) as f:
            resultado = json.load(f)
    resultado.update(campos)
    with open(caminho, "w") as f:
        json.dump(resultado, f, indent=2)

def _tar_com_submission(payload: dict) -> io.BytesIO:
    submission = {
        "task_delivered_id": payload["task_delivered_id"],
        "correction_strategy_id": payload["correction_strategy_id"],
        "question_score": payload["question_score"],
        "code_sent": payload["code_sent"],
        "test_cases": payload["test_cases"],
    }
    dados = json.dumps(submission, ensure_ascii=False).encode("utf-8")

    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        info = tarfile.TarInfo(name="submission.json")
        info.size = len(dados)
        tar.addfile(info, io.BytesIO(dados))
    tar_stream.seek(0)
    return tar_stream


def executar_sandbox(payload: dict) -> dict:
    inicio = time.time()
    container = None
    try:
        container = docker_client.containers.create(
            image=SANDBOX_IMAGE,
            working_dir="/app",
            command=["python", "corrigeQuestao.py"],
            mem_limit=MEM_LIMIT,
            memswap_limit=MEM_LIMIT,  # igual a mem_limit para nao usar swap
            cpu_period=100000,
            cpu_quota=CPU_QUOTA,
            network_disabled=True,
            pids_limit=64,
        )
        container.put_archive("/app", _tar_com_submission(payload))
        container.start()
    except Exception as exc:  # pega APIError e qualquer outro erro de preparo
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
        return {
            "veredito": "erro_infraestrutura",
            "saida": str(exc),
            "tempo_execucao_container_s": round(time.time() - inicio, 3),
        }

    try:
        try:
            resultado_wait = container.wait(timeout=TIMEOUT_SEGUNDOS)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            # tempo esgotado: mata o container e encerra aqui
            try:
                container.kill()
            except Exception:
                pass
            logs = "Tempo limite de execucao excedido."
            veredito = "tempo_limite_excedido"
        else:
            status_code = resultado_wait.get("StatusCode", -1)
            # limita o tamanho da saida para nao estourar memoria do worker
            logs = container.logs(tail=200).decode("utf-8", errors="replace")[:20000]

            container.reload()
            oom_killed = container.attrs.get("State", {}).get("OOMKilled", False)

            if status_code == 0:
                veredito = "concluida"
            elif oom_killed:
                veredito = "limite_memoria_excedido"
            elif ( "Resource temporarily unavailable" in logs
                    or "can't start new thread" in logs ):
                veredito = "limite_processos_excedido"
            else:
                veredito = "erro_execucao"
    except Exception as exc:
        logs = str(exc)
        veredito = "erro_infraestrutura"
    finally:
        tempo_execucao_container = round(time.time() - inicio, 3)
        try:
            container.remove(force=True)
        except Exception:
            pass

    return {
        "veredito": veredito,
        "saida": logs,
        "tempo_execucao_container_s": tempo_execucao_container,
    }


def processar_mensagem(channel, method, properties, body):
    # Mensagem malformada nunca vai funcionar: descarta em vez de reenfileirar
    try:
        payload = json.loads(body)
        task_delivered_id = payload["task_delivered_id"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f" [!] Mensagem invalida descartada: {exc}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return

    print(f" [x] Processando task_delivered {task_delivered_id}")

    try:
        # Executa o codigo de correcao
        resultado = executar_sandbox(payload)
        resultado["task_delivered_id"] = payload["task_delivered_id"]
        channel.basic_publish(
            exchange="",
            routing_key=RABBITMQ_QUEUE_GRADING_RESULTS,
            body=json.dumps(resultado),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                correlation_id=str(task_delivered_id),
            ),
            mandatory=True,
        )

        # Confirma fim do processamento
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as exc:
        #Ocorreu algum erro de infraestrutura
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        print(f" [!] Falha ao processar {task_delivered_id}: {exc}")


def main():
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        heartbeat=30,
        blocked_connection_timeout=30,
    )
    # Conectando ao RabbitMQ
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    
    # Declarando as filas
    # Se ja existem o RabbitMQ ignora
    channel.queue_declare(queue=RABBITMQ_QUEUE_GRADING_REQUESTS, durable=True)
    channel.queue_declare(queue=RABBITMQ_QUEUE_GRADING_RESULTS, durable=True)

    # ACK automatico desabilitado + prefetch=1: pega uma submissao por vez
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=RABBITMQ_QUEUE_GRADING_REQUESTS, on_message_callback=processar_mensagem)

    print(" [*] Corretor aguardando submissoes. CTRL+C para sair.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    connection.close()


if __name__ == "__main__":
    main()
