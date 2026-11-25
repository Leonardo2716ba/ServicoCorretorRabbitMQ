"""Regra de correcao: roda a submissao no sandbox e monta o resultado final."""
import json
import time

from sandbox import CONCLUIDA, run_in_sandbox


def parse_report(logs: str) -> dict:
    try:
        report = json.loads(logs)
        return report if isinstance(report, dict) else {"raw_output": logs}
    except (json.JSONDecodeError, TypeError):
        return {"raw_output": logs}


def grade_submission(payload: dict) -> dict:
    inicio = time.time()

    sandbox = run_in_sandbox(payload)
    report = parse_report(sandbox.logs)

    question_score = payload.get("question_score", 0.0)
    if sandbox.status == CONCLUIDA:
        question_score = report.get("NotaFinal", 0.0)

    return {
        **payload,
        "execution_status": sandbox.status,
        "question_score": question_score,
        "report": report,
        "container_runtime_seconds": round(time.time() - inicio, 3),
    }