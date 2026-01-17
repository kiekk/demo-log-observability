import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 20 },   // Ramp up to 20 VUs
    { duration: '6m', target: 30 },   // Stay at 30 VUs
    { duration: '2m', target: 0 },    // Ramp down to 0 VUs
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'], // 95% of requests should be below 1s
    http_req_failed: ['rate<0.05'],    // Error rate should be less than 5%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8080';

export default function () {
  // Mix of normal and slow requests
  const scenario = Math.random();

  if (scenario < 0.7) {
    // 70% normal requests
    const res = http.get(`${BASE_URL}/api/hello`);
    check(res, {
      'hello status is 200': (r) => r.status === 200,
    });
  } else {
    // 30% slow requests with random delay
    const delay = Math.floor(Math.random() * 200) + 100; // 100-300ms
    const res = http.get(`${BASE_URL}/api/slow?ms=${delay}`);
    check(res, {
      'slow status is 200': (r) => r.status === 200,
      'slow has delay_ms': (r) => r.json('delay_ms') !== undefined,
    });
  }

  sleep(Math.random() * 2 + 1); // Sleep 1-3 seconds
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';

  let summary = `\n${indent}Steady Test Summary:\n`;
  summary += `${indent}  Total Duration........: ${(data.state.testRunDurationMs / 1000 / 60).toFixed(2)} minutes\n`;
  summary += `${indent}  Checks................: ${data.metrics.checks.passes}/${data.metrics.checks.passes + data.metrics.checks.fails} passed\n`;
  summary += `${indent}  HTTP Requests.........: ${data.metrics.http_reqs.count} total\n`;
  summary += `${indent}  HTTP Req Duration.....: avg=${data.metrics.http_req_duration.avg.toFixed(2)}ms p(95)=${data.metrics.http_req_duration['p(95)'].toFixed(2)}ms\n`;
  summary += `${indent}  HTTP Req Failed.......: ${(data.metrics.http_req_failed.rate * 100).toFixed(2)}%\n`;
  summary += `${indent}  Iteration Duration....: avg=${data.metrics.iteration_duration.avg.toFixed(2)}ms\n`;

  return summary;
}
