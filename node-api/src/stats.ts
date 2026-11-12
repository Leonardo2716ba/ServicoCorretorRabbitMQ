export interface ResultEntry {
  task_delivered_id: number;
  execution_status: string;
  container_runtime_seconds: number;
  completedAt: number;
  question_score: number;
}

export const stats = {
  submitted: 0,
  completed: 0,
  firstSubmitAt: null as number | null,
  lastCompletedAt: null as number | null,
  results: [] as ResultEntry[],
};

export function resetStats(): void {
  stats.submitted = 0;
  stats.completed = 0;
  stats.firstSubmitAt = null;
  stats.lastCompletedAt = null;
  stats.results = [];
}



