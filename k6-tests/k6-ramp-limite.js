// Teste de rampa ate o limite da API de submissoes (Grafana k6)
//
// Sobe a taxa de requisicoes em degraus: PASSO, 2*PASSO, ... ate TAXA_MAX req/s.
// Cada degrau tem uma subida de RAMPA_S segundos e um patamar de PATAMAR_S segundos.
// So o patamar e medido: as requisicoes da subida recebem a tag nivel=rampa.
//
// O teste aborta sozinho quando a API quebra:
//   - falhas acima de ABORTAR_SE_FALHA em um degrau, ou
//   - k6 sem conseguir manter a taxa (MAX_DROPPED iteracoes descartadas).
//
// Este arquivo executa UMA repeticao. Use rodar-ramp.sh para repetir N vezes
// apagando as filas do RabbitMQ entre as repeticoes.
//
// Uso direto:
//   k6 run -e REP=1 k6-ramp-limite.js

import http from 'k6/http';
import exec from 'k6/execution';

// ---------- parametros (via -e NOME=valor) ----------
const API_URL = __ENV.API_URL || 'http://192.168.31.52:3000';
const REP = __ENV.REP || '1'; // numero da repeticao (so identifica o CSV)
const OUT_DIR = __ENV.OUT_DIR || 'resultados';
const TAXA_MAX = Number(__ENV.TAXA_MAX || 10000);
const PASSO = Number(__ENV.PASSO || 200);
const RAMPA_S = Number(__ENV.RAMPA_S || 10); // tempo para subir ate o degrau
const PATAMAR_S = Number(__ENV.PATAMAR_S || 20); // tempo segurando o degrau (medido)
const PRE_VUS = Number(__ENV.PRE_VUS || 1000);
const MAX_VUS = Number(__ENV.MAX_VUS || 1000);
const TIMEOUT_S = Number(__ENV.TIMEOUT_S || 10);
const MAX_ERR = Number(__ENV.MAX_ERR || 0.01); // criterio: falhas abaixo de 1%
const P95_MS = Number(__ENV.P95_MS || 1000); // criterio: p95 abaixo de 1000 ms
const ABORTAR_SE_FALHA = Number(__ENV.ABORTAR_SE_FALHA || 0.15); // aborta com 15% de falhas
const MAX_DROPPED = Number(__ENV.MAX_DROPPED || 20000); // aborta se o k6 nao acompanhar

// ---------- degraus ----------
const niveis = [];
for (let alvo = PASSO; alvo <= TAXA_MAX; alvo += PASSO) niveis.push(alvo);

const stages = [];
niveis.forEach((alvo) => {
  stages.push({ duration: `${RAMPA_S}s`, target: alvo }); // subida
  stages.push({ duration: `${PATAMAR_S}s`, target: alvo }); // patamar
});

const thresholds = {};
niveis.forEach((alvo) => {
  const sel = `{nivel:${alvo}}`;
  thresholds['http_req_failed' + sel] = [
    `rate<${MAX_ERR}`,
    { threshold: `rate<${ABORTAR_SE_FALHA}`, abortOnFail: true, delayAbortEval: '5s' },
  ];
  thresholds['http_req_duration' + sel] = [`p(95)<${P95_MS}`];
  // threshold sempre verdadeiro: so existe para criar o sub-metric usado no CSV
  thresholds['http_reqs' + sel] = ['count>=0'];
});
thresholds['dropped_iterations'] = [{ threshold: `count<${MAX_DROPPED}`, abortOnFail: true }];

export const options = {
  scenarios: {
    rampa: {
      executor: 'ramping-arrival-rate',
      exec: 'enviar',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: PRE_VUS,
      maxVUs: Math.max(MAX_VUS, PRE_VUS),
      stages,
      gracefulStop: '5s',
    },
  },
  thresholds,
  discardResponseBodies: true,
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// ---------- requisicao ----------
// Objeto reaproveitado em cada VU: somente o ID muda a cada iteração
const corpo = JSON.parse(open('./payload.json'));

const corpo_2 = {
  task_delivered_id: 0,
  correction_strategy_id: 1,
  question_score: 10,

  code_sent: `n = 1000
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
`,

  test_cases: [
    {
      id: 1,
      criterion: `1
1 3
ordenado=sim||4.0
trocas=247629||3.0
soma=4969660||3.0`,
      input: "",
      output: "ordenado=sim trocas=247629 soma=4969660\n"
    }
  ]
};




const base = {
  headers: { 'Content-Type': 'application/json' },
  timeout: `${TIMEOUT_S}s`,
  responseCallback: http.expectedStatuses(202), // so 202 conta como sucesso
};

// um objeto de parametros por nivel, para nao alocar um novo a cada requisicao
const paramsPorNivel = {};
['rampa', 'fim'].concat(niveis.map(String)).forEach((nivel) => {
  paramsPorNivel[nivel] = Object.assign({}, base, { tags: { nivel } });
});

// descobre em que fase da rampa o teste esta: subida ou patamar de um degrau
function nivelAtual() {
  const decorrido = (Date.now() - exec.scenario.startTime) / 1000;
  const janela = RAMPA_S + PATAMAR_S;
  const idx = Math.floor(decorrido / janela);
  if (idx >= niveis.length) return 'fim';
  return decorrido - idx * janela < RAMPA_S ? 'rampa' : String(niveis[idx]);
}

export function setup() {
  const baseId = Date.now() % 100000000;

  // requisicao de teste: aborta cedo se o payload for rejeitado pela validacao
  corpo.task_delivered_id = baseId - 1;
  const res = http.post(`${API_URL}/api/v1/grade`, JSON.stringify(corpo), base);
  if (res.status !== 202) {
    throw new Error(`Requisicao de teste falhou: status ${res.status}. Verifique API_URL e o payload.`);
  }
  return { baseId };
}

export function enviar(dados) {
  corpo.task_delivered_id = dados.baseId + exec.scenario.iterationInTest;
  http.post(`${API_URL}/api/v1/grade`, JSON.stringify(corpo), paramsPorNivel[nivelAtual()]);
}

// ---------- resultados ----------
function valor(metrica, chave) {
  if (!metrica || !metrica.values || metrica.values[chave] === undefined) return null;
  return metrica.values[chave];
}

function fmt(x, casas) {
  return x === null || x === undefined ? '' : x.toFixed(casas);
}

export function handleSummary(data) {
  let falhou = false;
  let limite = 0; // maior degrau sustentado antes do primeiro que falhou

  const resultados = niveis.map((alvo) => {
    const sel = `{nivel:${alvo}}`;
    const dur = data.metrics['http_req_duration' + sel];
    const reqs = valor(data.metrics['http_reqs' + sel], 'count');
    const falha = valor(data.metrics['http_req_failed' + sel], 'rate');
    const p95 = valor(dur, 'p(95)');
    const reais = reqs === null ? null : reqs / PATAMAR_S;

    let status = 'nao_atingiu'; // a rampa abortou antes de chegar neste degrau
    if (reqs !== null && reqs > 0) {
      const ok = falha < MAX_ERR && p95 < P95_MS && reais >= 0.95 * alvo;
      status = ok ? 'sim' : 'nao';
    }
    if (status === 'sim' && !falhou) limite = alvo;
    else falhou = true;

    if (status === 'nao_atingiu') {
      return { alvo, reqs: null, reais: null, falha: null, avg: null, med: null, p90: null, p95: null, p99: null, max: null, status };
    }

    return {
      alvo,
      reqs,
      reais,
      falha,
      avg: valor(dur, 'avg'),
      med: valor(dur, 'med'),
      p90: valor(dur, 'p(90)'),
      p95,
      p99: valor(dur, 'p(99)'),
      max: valor(dur, 'max'),
      status,
    };
  });

  const csv =
    [
      'repeticao,taxa_alvo_req_s,requisicoes,taxa_real_req_s,taxa_falha,avg_ms,med_ms,p90_ms,p95_ms,p99_ms,max_ms,passou',
    ]
      .concat(
        resultados.map((r) =>
          [
            REP,
            r.alvo,
            r.reqs === null ? 0 : r.reqs,
            fmt(r.reais, 1),
            fmt(r.falha, 4),
            fmt(r.avg, 1),
            fmt(r.med, 1),
            fmt(r.p90, 1),
            fmt(r.p95, 1),
            fmt(r.p99, 1),
            fmt(r.max, 1),
            r.status,
          ].join(','),
        ),
      )
      .join('\n') + '\n';

  const tabela = resultados.map(
    (r) =>
      `alvo ${String(r.alvo).padStart(5)} req/s  real ${fmt(r.reais, 0).padStart(5)}  ` +
      `falha ${fmt(r.falha === null ? null : r.falha * 100, 2).padStart(6)}%  ` +
      `p95 ${fmt(r.p95, 0).padStart(5)} ms  ${r.status}`,
  );

  const texto =
    `\n=== Repeticao ${REP} ===\n` +
    tabela.join('\n') +
    `\n\nLimite sustentado nesta repeticao: ${limite} req/s\n`;

  const saida = { stdout: texto };
  saida[`${OUT_DIR}/rep_${REP}.csv`] = csv;
  return saida;
}