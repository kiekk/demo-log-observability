import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
    stages: [
        { duration: '10s', target: 5 },
        { duration: '60s', target: 15 },
        { duration: '10s', target: 0 },
    ],
};

const BASE = __ENV.TARGET || 'http://buggy-service:8080';

// 100~200 중 i%3==0 (city='') 또는 i%7==0 (city=NULL) — broken city
const BROKEN_USER_IDS = [102, 105, 108, 111, 114, 119, 112, 126, 133, 140, 147, 154, 168, 189, 196];
const GOOD_USER_IDS = [1, 2, 50, 220, 245];

export default function () {
    const useBroken = Math.random() < 0.8;
    const arr = useBroken ? BROKEN_USER_IDS : GOOD_USER_IDS;
    const userId = arr[Math.floor(Math.random() * arr.length)];
    http.get(`${BASE}/api/users/${userId}/shipping`);
    sleep(0.2);
}
