import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
    stages: [
        { duration: '10s', target: 50 },
        { duration: '60s', target: 50 },
        { duration: '10s', target: 0 },
    ],
    http: {
        timeout: '15s',
    },
};

const BASE = __ENV.TARGET || 'http://buggy-service:8080';

export default function () {
    http.get(`${BASE}/api/reports/heavy`, { timeout: '15s' });
    sleep(0.1);
}
