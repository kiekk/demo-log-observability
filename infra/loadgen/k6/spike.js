import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 100 },  // Fast ramp up to 100 VUs
    { duration: '30s', target: 300 },  // Spike to 300 VUs
    { duration: '1m', target: 500 },   // Peak at 500 VUs
    { duration: '30s', target: 100 },  // Quick ramp down
    { duration: '10s', target: 0 },    // Recovery
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests should be below 2s (relaxed for spike)
    // No error rate threshold - we expect errors
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8080';

export default function () {
  const scenario = Math.random();

  if (scenario < 0.5) {
    // 50% error requests with high error rate
    const res = http.get(`${BASE_URL}/api/error?rate=0.3`);
    check(res, {
      'error endpoint responded': (r) => r.status === 200 || r.status === 500,
    });
  } else {
    // 50% burst requests generating many logs
    const lines = Math.floor(Math.random() * 50) + 50; // 50-100 lines
    const res = http.get(`${BASE_URL}/api/burst?lines=${lines}`);
    check(res, {
      'burst status is 200': (r) => r.status === 200,
      'burst has lines_generated': (r) => r.json('lines_generated') !== undefined,
    });
  }

  sleep(Math.random() * 0.5); // Short sleep 0-0.5 seconds for high load
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';

  let summary = `\n${indent}Spike Test Summary:\n`;
  summary += `${indent}  Total Duration........: ${(data.state.testRunDurationMs / 1000 / 60).toFixed(2)} minutes\n`;
  summary += `${indent}  Checks................: ${data.metrics.checks.passes}/${data.metrics.checks.passes + data.metrics.checks.fails} passed\n`;
  summary += `${indent}  HTTP Requests.........: ${data.metrics.http_reqs.count} total\n`;
  summary += `${indent}  HTTP Req Duration.....: avg=${data.metrics.http_req_duration.avg.toFixed(2)}ms p(95)=${data.metrics.http_req_duration['p(95)'].toFixed(2)}ms max=${data.metrics.http_req_duration.max.toFixed(2)}ms\n`;
  summary += `${indent}  HTTP Req Failed.......: ${(data.metrics.http_req_failed.rate * 100).toFixed(2)}%\n`;
  summary += `${indent}  Iteration Duration....: avg=${data.metrics.iteration_duration.avg.toFixed(2)}ms\n`;
  summary += `${indent}  VUs (max).............: ${data.metrics.vus.max}\n`;

  summary += `\n${indent}  NOTE: This spike test is designed to trigger alerts!\n`;
  summary += `${indent}  Check Grafana for:\n`;
  summary += `${indent}    - Error log spike in dashboard\n`;
  summary += `${indent}    - Alert firing for high error rate\n`;
  summary += `${indent}    - Log volume increase in burst panel\n`;

  return summary;
}
