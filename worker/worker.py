import os, io, json, time, tarfile, requests
import pika
import docker

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "runner-sandbox")
SANDBOX_DEFAULT_MEM_LIMIT = os.environ.get("SANDBOX_DEFAULT_MEM_LIMIT", "64m")
SANDBOX_CPU_QUOTA = int(os.environ.get("SANDBOX_CPU_QUOTA", "50000"))  # cpu_period padrao = 100000 # Equivale a 100%
SANDBOX_MAX_TIME_LIMIT_SECONDS = int(os.environ.get("SANDBOX_MAX_TIME_LIMIT_SECONDS"))

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_QUEUE_GRADING_REQUESTS = os.environ.get("RABBITMQ_QUEUE_GRADING_REQUESTS", "grading.requests")
RABBITMQ_QUEUE_GRADING_RESULTS = os.environ.get("RABBITMQ_QUEUE_GRADING_RESULTS", "grading.results")

MAX_EXECUTION_TIME_SECONDS="2"
RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")
os.makedirs(RESULTS_DIR, exist_ok=True)

docker_client = docker.from_env()

def container_runtime_seconds(payload: dict) -> io.BytesIO:
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

def create_sandbox(payload: dict):
    mem_limit = payload.get("sandbox_mem_limit") or SANDBOX_DEFAULT_MEM_LIMIT
    time_limit = payload.get("max_execution_time_seconds") or MAX_EXECUTION_TIME_SECONDS

    container = docker_client.containers.create(
        image=SANDBOX_IMAGE,
        working_dir="/app",
        command=["python", "corrigeQuestao.py", "submission.json", str(time_limit)],
        mem_limit=mem_limit,
        memswap_limit=mem_limit,
        cpu_period=100000,
        cpu_quota=SANDBOX_CPU_QUOTA,
        network_disabled=True,
        pids_limit=64
    )
    container.put_archive("/app", container_runtime_seconds(payload))
    container.start()
    return container

def execute_sandbox(container) -> tuple[str, str]:
    try:
        resultado_wait = container.wait(timeout=SANDBOX_MAX_TIME_LIMIT_SECONDS)

    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
        try:
            container.kill()
        except Exception:
            pass

        return "tempo_limite_container_excedido", "Tempo limite de execucao do container excedido."

    status_code = resultado_wait.get("StatusCode", -1)
    logs = container.logs(tail=200).decode("utf-8", errors="replace")[:20000]

    container.reload()
    oom_killed = container.attrs.get("State", {}).get("OOMKilled", False)

    state = container.attrs.get("State", {})

    print({
        "status_code": status_code,
        "oom_killed": state.get("OOMKilled"),
        "exit_code": state.get("ExitCode"),
        "error": state.get("Error"),
        "finished_at": state.get("FinishedAt")
    })

    if oom_killed: status = "limite_memoria_excedido"
    elif status_code == 0: status = "concluida"
    elif ( "Resource temporarily unavailable" in logs
            or "can't start new thread" in logs ):
        status = "limite_processos_excedido"
    else:
        status = "erro_execucao"
    return status, logs

def parse_report_to_json(logs: str) -> dict:
    try:
        report = json.loads(logs)
        return report if isinstance(report, dict) else {"raw_output": logs}
    except (json.JSONDecodeError, TypeError):
        return {"raw_output": logs}


def remove_sandbox(container) -> None:
    if container is not None:
        try:
            container.remove(force=True)
        except Exception as exc:
            print(f"[!] Erro ao remover container: {exc}")


def run_correction_sandbox(payload: dict) -> dict:
    inicio = time.time()
    container = None
    execution_status = "erro_infraestrutura"
    logs = ""
    question_score = payload.get("question_score", 0.0)

    try:
        container = create_sandbox(payload)
        execution_status, logs = execute_sandbox(container)
    except Exception as exc:
        execution_status, logs = "erro_infraestrutura", str(exc)
    finally:
        remove_sandbox(container)

    # Interpretação do relatório
    report_json = parse_report_to_json(logs)

    if execution_status == "concluida":
        question_score = report_json.get("NotaFinal", 0.0)
    payload.update({
        "execution_status": execution_status,
        "question_score": question_score,
        "report": report_json,
        "container_runtime_seconds": round(time.time() - inicio, 3)
    })

    return payload

def handle_correction_request(channel, method, properties, body):
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
        resultado = run_correction_sandbox(payload)
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

def start_worker():
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

    # ACK automatico desabilitado + prefetch=4: pega quatro submissao por vez
    channel.basic_qos(prefetch_count=4)
    channel.basic_consume(queue=RABBITMQ_QUEUE_GRADING_REQUESTS, on_message_callback=handle_correction_request)

    print(" [*] Corretor aguardando submissoes. CTRL+C para sair.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    connection.close()


if __name__ == "__main__":
    start_worker()
