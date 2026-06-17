import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
    stages: [
        { duration: '10s', target: 5 },
        { duration: '60s', target: 20 },
        { duration: '10s', target: 0 },
    ],
};

const BASE = __ENV.TARGET || 'http://buggy-service:8080';

export default function () {
    const items = Math.random() < 0.8 ? 0 : 2;  // 80% 0 나눗셈
    http.get(`${BASE}/api/cart/discount?items=${items}&total=100`);
    sleep(0.2);
}
