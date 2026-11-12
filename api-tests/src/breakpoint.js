// breakpoint.js
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { htmlReport } from "https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.1/index.js";

//const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000/api/v1/grade';
const BASE_URL = 'http://192.168.31.70:3000/api/v1/grade';
const START_ID = Number(__ENV.START_ID || 1);

export const options = {
  scenarios: {
    breakpoint_rate: {
      executor: 'ramping-arrival-rate',
      startRate: 3000,
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 1000,
      stages: [
        //{ duration: '1m', target: 500 },
        //{ duration: '1m', target: 1000 },
        //{ duration: '1m', target: 2000 },
        { duration: '3m', target: 4000 },
	{ duration: '2m', target: 4100 },
	{ duration: '2m', target: 4000 },
        //{ duration: '1m', target: 4000 },
        //{ duration: '1m', target: 5000 },
        //{ duration: '1m', target: 6000 },
        //{ duration: '1m', target: 7000 },
        //{ duration: '1m', target: 8000 },
        //{ duration: '1m', target: 9000 },
        //{ duration: '1m', target: 10000 },
      ],
    },
  },
  thresholds: {
    // abortOnFail encerra o teste no primeiro ponto de ruptura, que e o objetivo do breakpoint
    http_req_failed: [
      { threshold: 'rate<0.15', abortOnFail: true, delayAbortEval: '30s' },
    ],
    http_req_duration: [
      { threshold: 'p(99)<2000', abortOnFail: true, delayAbortEval: '30s' },
    ],
  },
};

const BASE_PAYLOAD = {
  task_delivered_id: 1,
  question_score: 0.0,
  is_pending: true,
  code_sent: 'v = int(input())\nprint(f"Hello World {v}")\n',
  correction_strategy_id: 1,
  test_cases: [
    { id: 1, criterion: '1\n2 1\nHello World||10.0', input: '5\n', output: '5\nHello World 5\n' },
    { id: 2, criterion: '1\n2 1\nBello World||10.0', input: '5\n', output: '5\nBello World fdfd5\n' },
  ],
};

export default function () {
  // iterationInTest e global no teste, entao cada requisicao tem um id unico
  const id = START_ID + exec.scenario.iterationInTest;
  const payload = { ...BASE_PAYLOAD, task_delivered_id: id };

  const res = http.post(BASE_URL, JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(res, {
    'status 202': (r) => r.status === 202,
  });
}

export function handleSummary(data) {
  return {
    'breakpoint-rate-report.html': htmlReport(data),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}
