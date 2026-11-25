"""Configuracao do worker: todas as variaveis de ambiente ficam aqui."""
import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    valor = os.getenv(name)
    if not valor:
        raise RuntimeError(f"Variavel de ambiente obrigatoria nao definida: {name}")
    return valor

# ---------- Sandbox (container que executa o codigo do aluno) ----------
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "runner-sandbox")
SANDBOX_DEFAULT_MEM_LIMIT = os.getenv("SANDBOX_DEFAULT_MEM_LIMIT", "32m")
# tempo maximo que o worker espera o container terminar
SANDBOX_MAX_TIME_LIMIT_SECONDS = int(os.getenv("SANDBOX_MAX_TIME_LIMIT_SECONDS", "2"))
SANDBOX_CPU_PERIOD = 100000
SANDBOX_CPU_QUOTA = int(os.getenv("SANDBOX_CPU_QUOTA", "90000"))  # 90000 / 100000 = 90% de um core
SANDBOX_PIDS_LIMIT = int(os.getenv("SANDBOX_PIDS_LIMIT", "64"))
# tempo por caso de teste quando a submissao nao informa
DEFAULT_TEST_CASE_TIME_LIMIT_SECONDS = os.getenv("DEFAULT_TEST_CASE_TIME_LIMIT_SECONDS", "2")

# ---------- RabbitMQ ----------
RABBITMQ_URL = _required("RABBITMQ_URL")
RABBITMQ_QUEUE_GRADING_REQUESTS = _required("RABBITMQ_QUEUE_GRADING_REQUESTS")
RABBITMQ_QUEUE_GRADING_RESULTS = _required("RABBITMQ_QUEUE_GRADING_RESULTS")
# mensagens que o worker puxa por vez (1 = distribuicao justa entre varios workers)
RABBITMQ_PREFETCH_COUNT = int(os.getenv("RABBITMQ_PREFETCH_COUNT", "2"))
RABBITMQ_HEARTBEAT_SECONDS = 30
RABBITMQ_BLOCKED_CONNECTION_TIMEOUT_SECONDS = 30

# nao e usado pelos modulos do worker; remova se nao for necessario
RESULTS_DIR = os.getenv("RESULTS_DIR", "/data/results")