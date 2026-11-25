"""Executa o codigo da submissao em um container isolado e classifica o resultado.

Esta camada conhece Docker e nada alem disso: recebe o payload, devolve
um veredito de execucao e a saida (logs) do container.
"""
import io
import json
import tarfile
from dataclasses import dataclass

import docker
import requests

import config

# vereditos possiveis da execucao
CONCLUIDA = "concluida"
LIMITE_MEMORIA_EXCEDIDO = "limite_memoria_excedido"
LIMITE_PROCESSOS_EXCEDIDO = "limite_processos_excedido"
TEMPO_LIMITE_CONTAINER_EXCEDIDO = "tempo_limite_container_excedido"
ERRO_EXECUCAO = "erro_execucao"
ERRO_INFRAESTRUTURA = "erro_infraestrutura"

# limita a saida lida do container para nao estourar a memoria do worker
LOG_TAIL_LINES = 200
LOG_MAX_CHARS = 20000

_docker_client = None


def get_docker_client():
    """Cria o cliente na primeira chamada (importar o modulo nao exige Docker)."""
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


@dataclass(frozen=True)
class SandboxResult:
    status: str
    logs: str


def _build_submission_tar(payload: dict) -> io.BytesIO:
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


def _create_container(payload: dict):
    mem_limit = payload.get("sandbox_mem_limit") or config.SANDBOX_DEFAULT_MEM_LIMIT
    time_limit = (
        payload.get("test_case_time_limit_seconds") or config.DEFAULT_TEST_CASE_TIME_LIMIT_SECONDS
    )
    return get_docker_client().containers.create(
        image=config.SANDBOX_IMAGE,
        working_dir="/app",
        command=["python", "corrigeQuestao.py", "submission.json", str(time_limit)],
        mem_limit=mem_limit,
        memswap_limit=mem_limit,  # igual a mem_limit para nao usar swap
        cpu_period=config.SANDBOX_CPU_PERIOD,
        cpu_quota=config.SANDBOX_CPU_QUOTA,
        network_disabled=True,
        pids_limit=config.SANDBOX_PIDS_LIMIT,
    )


def _wait_and_classify(container) -> SandboxResult:
    try:
        resultado_wait = container.wait(timeout=config.SANDBOX_MAX_TIME_LIMIT_SECONDS)
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
        try:
            container.kill()
        except Exception:
            pass
        return SandboxResult(
            TEMPO_LIMITE_CONTAINER_EXCEDIDO, "Tempo limite de execucao do container excedido."
        )

    status_code = resultado_wait.get("StatusCode", -1)
    logs = container.logs(tail=LOG_TAIL_LINES).decode("utf-8", errors="replace")[:LOG_MAX_CHARS]

    container.reload()
    state = container.attrs.get("State", {})
    oom_killed = state.get("OOMKilled", False)

    print({
        "status_code": status_code,
        "oom_killed": oom_killed,
        "exit_code": state.get("ExitCode"),
        "error": state.get("Error"),
        "finished_at": state.get("FinishedAt"),
    })

    if oom_killed:
        status = LIMITE_MEMORIA_EXCEDIDO
    elif status_code == 0:
        status = CONCLUIDA
    elif "Resource temporarily unavailable" in logs or "can't start new thread" in logs:
        status = LIMITE_PROCESSOS_EXCEDIDO
    else:
        status = ERRO_EXECUCAO
    return SandboxResult(status, logs)


def _remove_container(container) -> None:
    if container is None:
        return
    try:
        container.remove(force=True)
    except Exception as exc:
        print(f"[!] Erro ao remover container: {exc}")


def run_in_sandbox(payload: dict) -> SandboxResult:
    container = None
    try:
        container = _create_container(payload)
        # put_archive/start ficam depois da atribuicao: se falharem, o finally
        # ainda enxerga o container e remove (antes ele vazava)
        container.put_archive("/app", _build_submission_tar(payload))
        container.start()
        return _wait_and_classify(container)
    except Exception as exc:
        return SandboxResult(ERRO_INFRAESTRUTURA, str(exc))
    finally:
        _remove_container(container)