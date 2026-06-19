import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
    stages: [
        { duration: '10s', target: 10 },
        { duration: '60s', target: 30 },
        { duration: '10s', target: 0 },
    ],
};

const BASE = __ENV.TARGET || 'http://buggy-service:8080';

export default function () {
    // 큰 파일 + 매우 짧은 timeout → 서버가 streaming 중 클라이언트 끊김 → ClientAbortException
    http.get(`${BASE}/api/download/large?sizeKb=10240`, {
        timeout: '100ms',
    });
    sleep(0.3);
}
