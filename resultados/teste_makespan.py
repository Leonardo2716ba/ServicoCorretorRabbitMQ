#!/usr/bin/env python3
"""
Teste de makespan do opCoders Judge.

Para cada combinacao (numero de workers x numero de submissoes) roda N repeticoes.
As execucoes sao organizadas em rodadas: em cada rodada todas as combinacoes rodam
uma vez, em ordem aleatoria (seed fixa), e a mesma combinacao nunca roda duas vezes
seguidas. Cada execucao gera uma linha no CSV.

Se o script for interrompido, rode de novo com o mesmo comando: as execucoes que ja
terminaram com status ok sao puladas.

Makespan = lastCompletedAt - firstSubmitAt, ambos medidos pela API Express
(GET /api/v1/stats), ou seja, do primeiro POST aceito ate a ultima correcao entregue.

Exemplos:
    python makespan_benchmark.py --compose-dir /caminho/do/compose --dry-run
    python makespan_benchmark.py --compose-dir /caminho/do/compose
    python makespan_benchmark.py --compose-dir /caminho/do/compose \
        --workers 1 3 --submissions 20 --repetitions 2 --csv teste_rapido.csv
"""

import argparse
import csv
import os
import random
import shlex
import statistics
import subprocess
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

DEFAULT_WORKERS = [1, 3, 5, 7, 9, 11]
DEFAULT_SUBMISSIONS = [100, 400, 600, 800, 1000]
DEFAULT_REPETITIONS = 10

STATUS_OK_VALUES = ("completed", "concluida")
MAX_CONSECUTIVE_FAILURES = 10

CSV_FIELDS = [
    "run_order", "started_at", "workers", "submissions", "repetition", "status",
    "makespan_s", "throughput_per_s", "send_duration_s",
    "completed", "status_ok", "score_mean",
    "container_runtime_mean_s", "container_runtime_median_s",
    "container_runtime_p95_s", "container_runtime_max_s",
    "seed", "host_cpus", "notes",
]

# ---------------------------------------------------------------------------
# Carga de trabalho: bubble sort de 1000 numeros (codigo aceito pela analise estatica)
# ---------------------------------------------------------------------------

CODE_SENT = """n = 1000
vetor = []
x = 12345
for i in range(n):
    x = (x * 1103515245 + 12345) % 2147483648
    vetor.append(x % 10000)

soma_antes = 0
for i in range(n):
    soma_antes = soma_antes + vetor[i]

trocas = 0
for i in range(n):
    for j in range(n - i - 1):
        if vetor[j] > vetor[j + 1]:
            aux = vetor[j]
            vetor[j] = vetor[j + 1]
            vetor[j + 1] = aux
            trocas = trocas + 1

ordenado = 'sim'
soma_depois = 0
for i in range(n):
    soma_depois = soma_depois + vetor[i]
    if i < n - 1:
        if vetor[i] > vetor[i + 1]:
            ordenado = 'nao'

print(f'ordenado={ordenado} trocas={trocas} soma={soma_depois}')
"""

# formato do criterio: <n_linhas>, depois "<linha> <n_partes>" e "<texto>||<peso>" repetido n_partes vezes
TEST_CASES = [
    {
        "id": 1,
        "criterion": "1\n1 3\nordenado=sim||4.0\ntrocas=247629||3.0\nsoma=4969660||3.0",
        "input": "",
        "output": "ordenado=sim trocas=247629 soma=4969660\n",
    },
]


def build_base_payload():
    # ajuste os campos aqui se o dataValidation da API exigir outro formato
    return {
        "task_delivered_id": 0,
        "question_score": 0.0,
        "mem_limit": "32m",
        "test_case_time_limit_seconds": "2",
        "correction_strategy_id": 1,
        "is_pending": True,
        "code_sent": CODE_SENT,
        "test_cases": TEST_CASES,
    }


# ---------------------------------------------------------------------------
# Plano de execucao
# ---------------------------------------------------------------------------

def build_plan(workers_list, submissions_list, repetitions, seed):
    rng = random.Random(seed)
    configs = [(w, s) for w in workers_list for s in submissions_list]
    plan = []
    previous = None
    for repetition in range(1, repetitions + 1):
        order = configs[:]
        rng.shuffle(order)
        # a mesma combinacao nunca roda duas vezes seguidas (fronteira entre rodadas)
        if previous is not None and len(order) > 1 and order[0] == previous:
            swap = rng.randrange(1, len(order))
            order[0], order[swap] = order[swap], order[0]
        for workers, submissions in order:
            plan.append({
                "order": len(plan) + 1,
                "repetition": repetition,
                "workers": workers,
                "submissions": submissions,
            })
        previous = order[-1]
    return plan


def load_done(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "ok":
                done.add((int(row["workers"]), int(row["submissions"]), int(row["repetition"])))
    return done


def append_row(path, row):
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Acesso a API, RabbitMQ e Docker
# ---------------------------------------------------------------------------

class Api:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self._local = threading.local()

    def _session(self):
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def health(self):
        return self._session().get(f"{self.base}/", timeout=5).status_code == 200

    def reset(self):
        response = self._session().post(f"{self.base}/api/v1/stats/reset", timeout=15)
        response.raise_for_status()

    def stats(self):
        response = self._session().get(f"{self.base}/api/v1/stats", timeout=60)
        response.raise_for_status()
        return response.json()

    def submit(self, payload):
        response = self._session().post(f"{self.base}/api/v1/grade", json=payload, timeout=30)
        if response.status_code != 202:
            raise RuntimeError(f"POST /grade retornou {response.status_code}: {response.text[:300]}")


class RabbitAdmin:
    def __init__(self, base_url, user, password):
        self.base = base_url.rstrip("/")
        self.auth = (user, password)

    def queue(self, name):
        response = requests.get(f"{self.base}/api/queues/%2F/{name}", auth=self.auth, timeout=10)
        response.raise_for_status()
        return response.json()

    def purge(self, name):
        response = requests.delete(f"{self.base}/api/queues/%2F/{name}/contents", auth=self.auth, timeout=10)
        response.raise_for_status()


def run_compose(compose_cmd, compose_dir, extra_args):
    command = compose_cmd + extra_args
    result = subprocess.run(command, cwd=compose_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} falhou: {result.stderr.strip()[:300]}")


def scale_workers(compose_cmd, compose_dir, workers):
    run_compose(compose_cmd, compose_dir,
                ["up", "-d", "--no-deps", "--no-recreate", "--scale", f"worker={workers}", "worker"])


def wait_for_api(api, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if api.health():
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("API nao respondeu a tempo")


def wait_for_consumers(admin, queue, expected, poll_seconds, timeout=240):
    # espera o numero de consumidores da fila bater e ficar estavel por 3 leituras
    deadline = time.time() + timeout
    stable = 0
    while time.time() < deadline:
        consumers = admin.queue(queue).get("consumers", 0)
        stable = stable + 1 if consumers == expected else 0
        if stable >= 3:
            return
        time.sleep(poll_seconds)
    raise TimeoutError(f"fila {queue} nao chegou a {expected} consumidores")


def drain_queues(admin, requests_queue, results_queue, poll_seconds, timeout=240):
    # esvazia a fila de requisicoes e espera as duas filas zerarem (incluindo nao confirmadas)
    deadline = time.time() + timeout
    clean_reads = 0
    while time.time() < deadline:
        admin.purge(requests_queue)
        total = admin.queue(requests_queue).get("messages", 0) + admin.queue(results_queue).get("messages", 0)
        clean_reads = clean_reads + 1 if total == 0 else 0
        if clean_reads >= 3:
            return
        time.sleep(poll_seconds)
    raise TimeoutError("filas nao esvaziaram a tempo")


# ---------------------------------------------------------------------------
# Execucao de um lote e metricas
# ---------------------------------------------------------------------------

def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def poll_interval_for(n_submissions):
    # /stats devolve todos os resultados; em lotes grandes consulta com menos frequencia
    return 1.0 if n_submissions <= 1000 else 5.0


def run_batch(api, base_payload, n_submissions, send_threads, stall_timeout, poll_seconds, label=""):
    api.reset()
    initial = api.stats()
    if initial["submitted"] != 0 or initial["completed"] != 0:
        raise RuntimeError("stats nao zerou apos o reset (resultados atrasados de execucao anterior?)")

    stop = threading.Event()

    def send(task_delivered_id):
        if stop.is_set():
            return
        payload = dict(base_payload)
        payload["task_delivered_id"] = task_delivered_id
        try:
            api.submit(payload)
        except Exception:
            stop.set()
            raise

    send_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=send_threads) as pool:
        futures = [pool.submit(send, i) for i in range(1, n_submissions + 1)]
        for future in futures:
            future.result()
    send_duration = time.perf_counter() - send_started

    last_completed = -1
    last_progress = time.monotonic()
    last_print = 0.0
    while True:
        stats = api.stats()
        if stats["submitted"] != n_submissions:
            raise RuntimeError(f"API registrou {stats['submitted']} submissoes, esperado {n_submissions}")
        if stats["completed"] > last_completed:
            last_completed = stats["completed"]
            last_progress = time.monotonic()
        if stats["completed"] >= n_submissions:
            return stats, send_duration, "ok"
        if time.monotonic() - last_progress > stall_timeout:
            return stats, send_duration, "stalled"
        if time.monotonic() - last_print > 15:
            log(f"    {label}{stats['completed']}/{n_submissions} corrigidas")
            last_print = time.monotonic()
        time.sleep(poll_seconds)


def status_of(result):
    return result.get("execution_status") or result.get("veredito")


def runtime_of(result):
    value = result.get("container_runtime_seconds")
    return value if value is not None else result.get("tempo_execucao_container_s")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def summarize(stats, send_duration):
    summary = {
        "completed": stats.get("completed", 0),
        "send_duration_s": round(send_duration, 3),
    }
    first, last = stats.get("firstSubmitAt"), stats.get("lastCompletedAt")
    if first and last:
        makespan = (last - first) / 1000.0
        summary["makespan_s"] = round(makespan, 3)
        if makespan > 0:
            summary["throughput_per_s"] = round(stats["completed"] / makespan, 3)

    results = stats.get("results") or []
    statuses = [status_of(r) for r in results]
    if any(statuses):
        summary["status_ok"] = sum(1 for s in statuses if s in STATUS_OK_VALUES)
    scores = [r["question_score"] for r in results if isinstance(r.get("question_score"), (int, float))]
    if scores:
        summary["score_mean"] = round(statistics.mean(scores), 3)
    runtimes = [runtime_of(r) for r in results]
    runtimes = [v for v in runtimes if isinstance(v, (int, float))]
    if runtimes:
        summary["container_runtime_mean_s"] = round(statistics.mean(runtimes), 3)
        summary["container_runtime_median_s"] = round(statistics.median(runtimes), 3)
        summary["container_runtime_p95_s"] = round(percentile(runtimes, 0.95), 3)
        summary["container_runtime_max_s"] = round(max(runtimes), 3)
    return summary


def check_sanity(stats):
    # confere uma vez, no primeiro warm-up, se o payload esta sendo corrigido como esperado
    results = stats.get("results") or []
    statuses = {status_of(r) for r in results}
    scores = [r["question_score"] for r in results if isinstance(r.get("question_score"), (int, float))]
    if not any(statuses):
        log("AVISO: a API nao repassa execution_status/question_score; aplique o patch em stats.ts e rabbitmq.ts")
        return
    log(f"    warm-up: status={sorted(str(s) for s in statuses)} score_medio={statistics.mean(scores) if scores else 'n/a'}")
    if not statuses.issubset(set(STATUS_OK_VALUES)) or (scores and statistics.mean(scores) < 10.0):
        log("AVISO: o warm-up nao terminou 100% completed com nota 10.0; confira o payload antes de seguir")


def prepare_workers(args, compose_cmd, api, admin, base_payload, workers):
    scale_workers(compose_cmd, args.compose_dir, workers)
    wait_for_consumers(admin, args.requests_queue, workers, args.rabbit_poll_seconds)
    drain_queues(admin, args.requests_queue, args.results_queue, args.rabbit_poll_seconds)
    warmup_size = max(4, 2 * workers)
    stats, _, status = run_batch(api, base_payload, warmup_size, args.send_threads,
                                 args.stall_timeout, 1.0, label="warm-up ")
    if status != "ok":
        raise RuntimeError("warm-up nao completou")
    return stats


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Teste de makespan do opCoders Judge")
    parser.add_argument("--compose-dir", default=".", help="pasta do docker-compose.yml")
    parser.add_argument("--compose-cmd", default="docker compose")
    parser.add_argument("--api-url", default="http://localhost:3000")
    parser.add_argument("--rabbit-url", default="http://localhost:15672", help="API de gerenciamento do RabbitMQ")
    parser.add_argument("--rabbit-user", default="guest")
    parser.add_argument("--rabbit-password", default="guest")
    parser.add_argument("--requests-queue", default="grading.requests")
    parser.add_argument("--results-queue", default="grading.results")
    parser.add_argument("--csv", default="makespan_results.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", nargs="+", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--submissions", nargs="+", type=int, default=DEFAULT_SUBMISSIONS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--stall-timeout", type=float, default=180.0,
                        help="aborta a execucao se nenhuma correcao terminar por este tempo (s)")
    parser.add_argument("--send-threads", type=int, default=8)
    parser.add_argument("--cooldown", type=float, default=10.0, help="pausa entre execucoes (s)")
    parser.add_argument("--rabbit-poll-seconds", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true", help="so mostra a ordem das execucoes")
    return parser.parse_args()


def print_summary(path):
    groups = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] == "ok" and row["makespan_s"]:
                groups[(int(row["submissions"]), int(row["workers"]))].append(float(row["makespan_s"]))
    if not groups:
        return
    print("\nsubmissoes  workers  n   makespan medio (s)  desvio (s)")
    for (submissions, workers) in sorted(groups):
        values = groups[(submissions, workers)]
        deviation = statistics.stdev(values) if len(values) > 1 else 0.0
        print(f"{submissions:>10}  {workers:>7}  {len(values):<3} {statistics.mean(values):>18.2f}  {deviation:>10.2f}")


def main():
    args = parse_args()
    plan = build_plan(args.workers, args.submissions, args.repetitions, args.seed)
    done = load_done(args.csv)
    pending = [e for e in plan if (e["workers"], e["submissions"], e["repetition"]) not in done]
    log(f"plano: {len(plan)} execucoes, {len(plan) - len(pending)} ja concluidas, {len(pending)} pendentes")

    if args.dry_run:
        for entry in pending:
            print(f"#{entry['order']:>3}  rodada {entry['repetition']}  "
                  f"workers={entry['workers']:>2}  submissoes={entry['submissions']}")
        return

    api = Api(args.api_url)
    admin = RabbitAdmin(args.rabbit_url, args.rabbit_user, args.rabbit_password)
    compose_cmd = shlex.split(args.compose_cmd)
    base_payload = build_base_payload()

    run_compose(compose_cmd, args.compose_dir, ["up", "-d", "--no-recreate"])
    wait_for_api(api)

    current_workers = None
    sanity_checked = False
    consecutive_failures = 0

    try:
        for position, entry in enumerate(pending, start=1):
            log(f"execucao {position}/{len(pending)} (#{entry['order']}): workers={entry['workers']} "
                f"submissoes={entry['submissions']} rodada={entry['repetition']}")
            row = dict.fromkeys(CSV_FIELDS, "")
            row.update({
                "run_order": entry["order"], "workers": entry["workers"],
                "submissions": entry["submissions"], "repetition": entry["repetition"],
                "seed": args.seed, "host_cpus": os.cpu_count(),
            })
            try:
                if entry["workers"] != current_workers:
                    warmup_stats = prepare_workers(args, compose_cmd, api, admin, base_payload, entry["workers"])
                    current_workers = entry["workers"]
                    if not sanity_checked:
                        check_sanity(warmup_stats)
                        sanity_checked = True
                row["started_at"] = datetime.now().isoformat(timespec="seconds")
                stats, send_duration, status = run_batch(
                    api, base_payload, entry["submissions"], args.send_threads, args.stall_timeout,
                    poll_interval_for(entry["submissions"]))
                row.update(summarize(stats, send_duration))
                row["status"] = status
                if status != "ok":
                    # execucao incompleta: o makespan parcial enganaria a analise
                    row["makespan_s"] = ""
                    row["throughput_per_s"] = ""
                    row["notes"] = f"sem progresso por {args.stall_timeout:.0f}s"
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                row["status"] = "error"
                row["notes"] = str(exc)[:300]

            append_row(args.csv, row)
            log(f"    status={row['status']} makespan={row['makespan_s'] or '-'}s {row['notes']}")

            if row["status"] == "ok":
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                current_workers = None  # forca preparar os workers de novo na proxima execucao
                try:
                    run_compose(compose_cmd, args.compose_dir, ["restart", "worker"])
                except Exception as exc:
                    log(f"    falha ao reiniciar workers: {exc}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log(f"{MAX_CONSECUTIVE_FAILURES} falhas seguidas: abortando. Corrija e rode de novo (retoma de onde parou).")
                    break
            time.sleep(args.cooldown)
    except KeyboardInterrupt:
        log("interrompido; a execucao em andamento nao foi gravada. Rode de novo para retomar.")

    print_summary(args.csv)


if __name__ == "__main__":
    main()
