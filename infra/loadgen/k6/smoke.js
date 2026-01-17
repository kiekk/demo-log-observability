import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 3 },  // Ramp up to 3 VUs
    { duration: '30s', target: 3 },  // Stay at 3 VUs
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests should be below 500ms
    http_req_failed: ['rate<0.01'],   // Error rate should be less than 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8080';

export default function () {
  // Test /api/hello endpoint
  const res = http.get(`${BASE_URL}/api/hello`);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'response has message': (r) => r.json('message') !== undefined,
  });

  sleep(1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;

  let summary = `\n${indent}Smoke Test Summary:\n`;
  summary += `${indent}  Checks................: ${data.metrics.checks.passes}/${data.metrics.checks.passes + data.metrics.checks.fails} passed\n`;
  summary += `${indent}  HTTP Requests.........: ${data.metrics.http_reqs.count} total\n`;
  summary += `${indent}  HTTP Req Duration.....: avg=${data.metrics.http_req_duration.avg.toFixed(2)}ms p(95)=${data.metrics.http_req_duration['p(95)'].toFixed(2)}ms\n`;
  summary += `${indent}  HTTP Req Failed.......: ${(data.metrics.http_req_failed.rate * 100).toFixed(2)}%\n`;

  return summary;
}
