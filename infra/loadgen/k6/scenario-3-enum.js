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
const STATUSES_OK = ['CREATED', 'PAID'];
const STATUSES_BAD = ['LEGACY_TYPE', 'UNKNOWN_STATUS'];

export default function () {
    const useBad = Math.random() < 0.8;
    const status = useBad
        ? STATUSES_BAD[Math.floor(Math.random() * STATUSES_BAD.length)]
        : STATUSES_OK[Math.floor(Math.random() * STATUSES_OK.length)];

    const body = JSON.stringify({ userId: 1, status: status, totalAmount: 1000 });
    http.post(`${BASE}/api/orders`, body, {
        headers: { 'Content-Type': 'application/json' },
    });
    sleep(0.2);
}
