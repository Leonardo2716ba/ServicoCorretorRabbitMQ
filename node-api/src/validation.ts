export interface dataObject {
  task_delivered_id: number;
  question_score: number;
  is_pending: boolean;
  code_sent: string;
  correction_strategy_id: number;
  test_cases: any[];
}

function isNull(value: unknown): boolean {
  return value == null;
}

export function dataValidation(object: dataObject) {
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
    errors,
  };
}