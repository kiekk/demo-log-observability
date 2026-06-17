import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
    stages: [
        { duration: '10s', target: 5 },
        { duration: '60s', target: 20 },  // 5분간 ERROR > 10개 임계값 빠르게 도달
        { duration: '10s', target: 0 },
    ],
};

const BASE = __ENV.TARGET || 'http://buggy-service:8080';

export default function () {
    // 80% 실패 케이스 (없는 사용자)
    const userId = Math.random() < 0.8 ? 999 : 1;
    http.get(`${BASE}/api/users/${userId}/profile`);
    sleep(0.2);
}
