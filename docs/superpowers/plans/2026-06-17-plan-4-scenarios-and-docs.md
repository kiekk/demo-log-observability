# Plan 4: 시나리오 4~6 + 대시보드 + DEMO_GUIDE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** demo-buggy-service에 시나리오 4 (DATA_ANOMALY), 5 (INFRA_ISSUE), 6 (BENIGN_ERROR) 코드를 추가하고 git tag로 분리. 각 시나리오용 k6 스크립트 작성. ai-bot 자체 동작을 시각화하는 Grafana 대시보드 추가 (Loki 기반). 마지막으로 DEMO_GUIDE.md로 시연 절차 정리.

**Architecture:** demo-buggy-service에 endpoint 3개 추가 (`/api/orders/{id}/shipping`, `/api/reports/heavy`, `/api/download/large`). 시나리오 4는 Plan 1에서 이미 심어둔 V2 seed의 빈 city 데이터를 활용. 시나리오 5는 트랜잭션 + 3초 sleep으로 HikariCP 풀(max=10) 고갈 유도. 시나리오 6은 짧은 timeout k6 + streaming response로 broken pipe 유발. Grafana 대시보드는 ai-bot stdout JSON 로그를 Loki에서 LogQL로 집계.

**Tech Stack:** Plan 1~3 스택 유지. 신규 의존성 없음.

**관련 문서:**
- spec: `docs/superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md` (Phase 8~9, 시나리오 4~6)
- 이전 plans: 1, 2, 3 완료 가정

---

## 사전 작업

- [ ] **A. Plan 3 완료 확인**
  - 시나리오 1~3 트리거 시 GitHub에 Draft PR이 실제로 생성되는 것 확인
  - ai-bot 로그에서 카테고리 분기, Slack 메시지 차별화 확인

- [ ] **B. demo-buggy-service main 브랜치 protection 켰는지 재확인**
  - 시나리오 4~6 시연 시에도 의도적 버그가 main에 유지되어야 함

---

## File Structure

```
demo-buggy-service/                            ★ git submodule (Plan 1 이후)
├── src/main/kotlin/com/example/buggy/
│   ├── controller/
│   │   ├── ShippingController.kt              (Task 1 — 시나리오 4)
│   │   ├── ReportController.kt                (Task 3 — 시나리오 5)
│   │   └── DownloadController.kt              (Task 5 — 시나리오 6)
│   ├── service/
│   │   ├── ShippingService.kt                 (Task 1)
│   │   ├── ReportService.kt                   (Task 3)
│   │   └── DownloadService.kt                 (Task 5)
│   └── dto/
│       ├── ShippingResponse.kt                (Task 1)
│       └── ReportResponse.kt                  (Task 3)
└── src/test/kotlin/com/example/buggy/controller/
    ├── ShippingControllerTest.kt              (Task 1)
    ├── ReportControllerTest.kt                (Task 3)
    └── DownloadControllerTest.kt              (Task 5)

$REPO/
├── infra/loadgen/k6/
│   ├── scenario-4-data.js                     (Task 2)
│   ├── scenario-5-dbpool.js                   (Task 4)
│   └── scenario-6-benign.js                   (Task 6)
├── infra/grafana/dashboards/
│   └── ai-bot-overview.json                   (Task 7)
└── docs/
    ├── DEMO_GUIDE.md                          (Task 8)
    └── ARCHITECTURE.md                        (Task 9)
```

---

## Task 1: 시나리오 4 — ShippingController (DATA_ANOMALY)

**Files:**
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/controller/ShippingController.kt`
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/service/ShippingService.kt`
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/dto/ShippingResponse.kt`
- Create: `demo-buggy-service/src/test/kotlin/com/example/buggy/controller/ShippingControllerTest.kt`

**의도된 동작**: `user.address.city`를 사용해서 배송비 계산. 코드는 정상 (null 체크 있음). 하지만 Plan 1의 V2 seed가 user_id 100~200 구간 일부에 city='' 또는 NULL을 심어놨으므로, 이 구간에서 호출하면 `IllegalArgumentException("city is blank")`. AI 봇은 이걸 DATA_ANOMALY로 분류해야 함 (코드 결함이 아닌 데이터 정합성 문제).

- [ ] **Step 1: 시나리오 1~3 git tag로 돌아가서 작업 시작점 확인**

Run:
```bash
cd ~/dev/demo-buggy-service
git checkout main
git status
```

Expected: main 브랜치 깨끗.

- [ ] **Step 2: ShippingResponse DTO**

Create `src/main/kotlin/com/example/buggy/dto/ShippingResponse.kt`:

```kotlin
package com.example.buggy.dto

data class ShippingResponse(
    val userId: Long,
    val orderId: Long,
    val city: String,
    val shippingFee: Int,
)
```

- [ ] **Step 3: 통합 테스트 — 정상/실패 모두**

Create `src/test/kotlin/com/example/buggy/controller/ShippingControllerTest.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.support.PostgresTestContainer
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@SpringBootTest
@AutoConfigureMockMvc
class ShippingControllerTest {
    @Autowired private lateinit var mvc: MockMvc

    companion object {
        @JvmStatic
        @DynamicPropertySource
        fun props(registry: DynamicPropertyRegistry) {
            val pg = PostgresTestContainer.instance
            registry.add("spring.datasource.url") { pg.jdbcUrl }
            registry.add("spring.datasource.username") { pg.username }
            registry.add("spring.datasource.password") { pg.password }
        }
    }

    @Test
    fun `valid user with proper address returns 200`() {
        // user_id=1은 V2 seed에서 정상 city
        mvc.get("/api/users/1/shipping").andExpect { status { isOk() } }
    }

    @Test
    fun `user in 100-200 with broken city returns 500 (data anomaly, not code bug)`() {
        // user_id=102, 105 등은 V2 seed에서 city='' 또는 NULL (i % 3 == 0 또는 i % 7 == 0)
        // 102 % 3 == 0 → city=''
        mvc.get("/api/users/102/shipping").andExpect { status { is5xxServerError() } }
    }
}
```

- [ ] **Step 4: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.ShippingControllerTest"
```

Expected: FAIL — 404 (컨트롤러 없음)

- [ ] **Step 5: ShippingService 구현 — 정상적인 null 체크 + isBlank 체크 누락**

Create `src/main/kotlin/com/example/buggy/service/ShippingService.kt`:

```kotlin
package com.example.buggy.service

import com.example.buggy.dto.ShippingResponse
import com.example.buggy.repository.AddressRepository
import com.example.buggy.repository.UserRepository
import org.springframework.stereotype.Service

@Service
class ShippingService(
    private val users: UserRepository,
    private val addresses: AddressRepository,
) {
    fun calculate(userId: Long): ShippingResponse {
        val user = users.findById(userId).orElseThrow {
            NoSuchElementException("user $userId not found")
        }
        val address = addresses.findByUserId(userId)
            ?: throw IllegalStateException("address not found for user $userId")

        // null 체크는 했지만 빈 문자열 체크는 안 함 — 의도된 데이터 정합성 가정
        val city = address.city ?: throw IllegalArgumentException("city is null")
        require(city.isNotEmpty()) { "city is blank" }   // 빈 문자열일 때 폭발

        val fee = cityShippingFee(city)
        return ShippingResponse(
            userId = user.id!!,
            orderId = 0L,  // 시나리오에서는 dummy
            city = city,
            shippingFee = fee,
        )
    }

    private fun cityShippingFee(city: String): Int =
        if (city.startsWith("City")) 3000 else 5000
}
```

- [ ] **Step 6: ShippingController 구현**

Create `src/main/kotlin/com/example/buggy/controller/ShippingController.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.dto.ShippingResponse
import com.example.buggy.service.ShippingService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/users")
class ShippingController(
    private val shippingService: ShippingService,
) {
    @GetMapping("/{userId}/shipping")
    fun getShipping(@PathVariable userId: Long): ShippingResponse {
        return shippingService.calculate(userId)
    }
}
```

- [ ] **Step 7: 테스트 재실행**

Run:
```bash
./gradlew test --tests "com.example.buggy.controller.ShippingControllerTest"
```

Expected: PASS (2 tests)

- [ ] **Step 8: Commit + tag**

```bash
cd ~/dev/demo-buggy-service
git add src/main/kotlin/com/example/buggy/controller/ShippingController.kt \
        src/main/kotlin/com/example/buggy/service/ShippingService.kt \
        src/main/kotlin/com/example/buggy/dto/ShippingResponse.kt \
        src/test/kotlin/com/example/buggy/controller/ShippingControllerTest.kt
git commit -m "feat(scenario-4): ShippingService relies on city — seed data anomaly triggers IllegalArgumentException"
git tag scenario-4
git push --tags
git push
```

---

## Task 2: 시나리오 4 k6 스크립트

**Files:**
- Create: `$REPO/infra/loadgen/k6/scenario-4-data.js`

- [ ] **Step 1: k6 스크립트 작성**

Create `$REPO/infra/loadgen/k6/scenario-4-data.js`:

```javascript
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

// 100~200 구간 중 i%3==0 또는 i%7==0인 user_id가 broken city
const BROKEN_USER_IDS = [102, 105, 108, 111, 114, 105, 119, 112, 126, 133, 140];
const GOOD_USER_IDS = [1, 2, 50, 220];

export default function () {
    const useBroken = Math.random() < 0.8;
    const arr = useBroken ? BROKEN_USER_IDS : GOOD_USER_IDS;
    const userId = arr[Math.floor(Math.random() * arr.length)];
    http.get(`${BASE}/api/users/${userId}/shipping`);
    sleep(0.2);
}
```

- [ ] **Step 2: Commit (k6는 메인 레포)**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add infra/loadgen/k6/scenario-4-data.js
git commit -m "feat(loadgen): scenario-4 k6 — biased toward broken user_id range"
```

---

## Task 3: 시나리오 5 — ReportController (INFRA_ISSUE)

**Files:**
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/controller/ReportController.kt`
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/service/ReportService.kt`
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/dto/ReportResponse.kt`
- Create: `demo-buggy-service/src/test/kotlin/com/example/buggy/controller/ReportControllerTest.kt`

**의도된 동작**: 트랜잭션 안에서 JPA 쿼리 1회 + `Thread.sleep(3000)`. 동시 호출 30개 이상이면 HikariCP 풀(max=10) 대기 타임아웃 → `SQLTransientConnectionException`. AI 봇은 INFRA_ISSUE로 분류해야 함.

- [ ] **Step 1: ReportResponse DTO**

Create `src/main/kotlin/com/example/buggy/dto/ReportResponse.kt`:

```kotlin
package com.example.buggy.dto

data class ReportResponse(
    val userCount: Long,
    val computedAt: String,
    val elapsedMs: Long,
)
```

- [ ] **Step 2: 통합 테스트 — 단일 요청은 OK, 동시 요청은 일부 실패 (timing 검증은 어려우니 단일 OK만 검증)**

Create `src/test/kotlin/com/example/buggy/controller/ReportControllerTest.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.support.PostgresTestContainer
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@SpringBootTest
@AutoConfigureMockMvc
class ReportControllerTest {
    @Autowired private lateinit var mvc: MockMvc

    companion object {
        @JvmStatic
        @DynamicPropertySource
        fun props(registry: DynamicPropertyRegistry) {
            val pg = PostgresTestContainer.instance
            registry.add("spring.datasource.url") { pg.jdbcUrl }
            registry.add("spring.datasource.username") { pg.username }
            registry.add("spring.datasource.password") { pg.password }
            // 테스트는 작은 풀로 실행해도 단일 요청은 OK
            registry.add("spring.datasource.hikari.maximum-pool-size") { "5" }
        }
    }

    @Test
    fun `single heavy report request returns 200 (slow but ok)`() {
        // 3초 sleep이 있어서 timeout 주의
        mvc.get("/api/reports/heavy").andExpect { status { isOk() } }
    }
}
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.ReportControllerTest"
```

Expected: FAIL — 404

- [ ] **Step 4: ReportService 구현**

Create `src/main/kotlin/com/example/buggy/service/ReportService.kt`:

```kotlin
package com.example.buggy.service

import com.example.buggy.dto.ReportResponse
import com.example.buggy.repository.UserRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.OffsetDateTime

@Service
class ReportService(
    private val users: UserRepository,
) {
    @Transactional
    fun heavyReport(): ReportResponse {
        val start = System.currentTimeMillis()
        // 의도적: 트랜잭션 안에서 작업이 오래 걸림 → connection을 오래 쥠 → 풀 고갈
        val count = users.count()
        Thread.sleep(3_000)
        val elapsed = System.currentTimeMillis() - start
        return ReportResponse(
            userCount = count,
            computedAt = OffsetDateTime.now().toString(),
            elapsedMs = elapsed,
        )
    }
}
```

- [ ] **Step 5: ReportController 구현**

Create `src/main/kotlin/com/example/buggy/controller/ReportController.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.dto.ReportResponse
import com.example.buggy.service.ReportService
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/reports")
class ReportController(
    private val reportService: ReportService,
) {
    @GetMapping("/heavy")
    fun heavy(): ReportResponse = reportService.heavyReport()
}
```

- [ ] **Step 6: 테스트 재실행**

Run:
```bash
./gradlew test --tests "com.example.buggy.controller.ReportControllerTest"
```

Expected: PASS (1 test, ~3초 소요)

- [ ] **Step 7: Commit + tag**

```bash
cd ~/dev/demo-buggy-service
git add src/main/kotlin/com/example/buggy/controller/ReportController.kt \
        src/main/kotlin/com/example/buggy/service/ReportService.kt \
        src/main/kotlin/com/example/buggy/dto/ReportResponse.kt \
        src/test/kotlin/com/example/buggy/controller/ReportControllerTest.kt
git commit -m "feat(scenario-5): ReportController with 3s sleep in transaction — exhausts HikariCP under load"
git tag scenario-5
git push --tags
git push
```

---

## Task 4: 시나리오 5 k6 스크립트

**Files:**
- Create: `$REPO/infra/loadgen/k6/scenario-5-dbpool.js`

- [ ] **Step 1: k6 스크립트 작성**

Create `$REPO/infra/loadgen/k6/scenario-5-dbpool.js`:

```javascript
import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
    // HikariCP max=10. 50 VU가 동시에 3초짜리 요청을 → 풀 고갈 → 일부 SQLTransientConnectionException
    stages: [
        { duration: '10s', target: 50 },
        { duration: '60s', target: 50 },
        { duration: '10s', target: 0 },
    ],
    // 응답이 느려서 timeout 길게
    http: {
        timeout: '15s',
    },
};

const BASE = __ENV.TARGET || 'http://buggy-service:8080';

export default function () {
    http.get(`${BASE}/api/reports/heavy`, { timeout: '15s' });
    // VU가 다시 요청 안 보내고 대기 — connection 점유 효과 강화
    sleep(0.1);
}
```

- [ ] **Step 2: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add infra/loadgen/k6/scenario-5-dbpool.js
git commit -m "feat(loadgen): scenario-5 k6 — 50 VU heavy report to exhaust HikariCP pool"
```

---

## Task 5: 시나리오 6 — DownloadController (BENIGN_ERROR)

**Files:**
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/controller/DownloadController.kt`
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/service/DownloadService.kt`
- Create: `demo-buggy-service/src/test/kotlin/com/example/buggy/controller/DownloadControllerTest.kt`

**의도된 동작**: 1MB 청크를 여러 번에 걸쳐 OutputStream에 write. 클라이언트가 timeout으로 일찍 끊으면 `ClientAbortException`. AI 봇은 BENIGN_ERROR로 분류 (비즈니스 로직 정상, ExceptionHandler 추가 권장).

- [ ] **Step 1: 통합 테스트 — 정상 케이스만 (timeout 시뮬레이션은 어려움)**

Create `src/test/kotlin/com/example/buggy/controller/DownloadControllerTest.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.support.PostgresTestContainer
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.content
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@SpringBootTest
@AutoConfigureMockMvc
class DownloadControllerTest {
    @Autowired private lateinit var mvc: MockMvc

    companion object {
        @JvmStatic
        @DynamicPropertySource
        fun props(registry: DynamicPropertyRegistry) {
            val pg = PostgresTestContainer.instance
            registry.add("spring.datasource.url") { pg.jdbcUrl }
            registry.add("spring.datasource.username") { pg.username }
            registry.add("spring.datasource.password") { pg.password }
        }
    }

    @Test
    fun `large download returns 200 and bytes when client waits`() {
        val response = mvc.get("/api/download/large?sizeKb=10").andReturn().response
        assert(response.status == 200)
        assert(response.contentAsByteArray.size >= 10 * 1024)
    }
}
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.DownloadControllerTest"
```

Expected: FAIL — 404

- [ ] **Step 3: DownloadService 구현**

Create `src/main/kotlin/com/example/buggy/service/DownloadService.kt`:

```kotlin
package com.example.buggy.service

import jakarta.servlet.http.HttpServletResponse
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

@Service
class DownloadService {
    private val logger = LoggerFactory.getLogger(javaClass)

    fun streamLarge(sizeKb: Int, response: HttpServletResponse) {
        response.contentType = "application/octet-stream"
        response.setHeader("Content-Disposition", "attachment; filename=large.bin")

        val chunk = ByteArray(1024) { i -> (i % 256).toByte() }
        val out = response.outputStream
        try {
            repeat(sizeKb) { i ->
                out.write(chunk)
                if (i % 100 == 0) {
                    out.flush()
                    Thread.sleep(50)  // 클라이언트 timeout 유도용 지연
                }
            }
            out.flush()
        } catch (e: Exception) {
            // 의도적: ExceptionHandler 없음 → ClientAbortException이 ERROR 로그로 떠올라 알림 발화
            // AI 봇이 BENIGN_ERROR로 분류해서 ExceptionHandler PR 만들어야 함
            logger.error("download interrupted", e)
            throw e
        }
    }
}
```

- [ ] **Step 4: DownloadController 구현**

Create `src/main/kotlin/com/example/buggy/controller/DownloadController.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.service.DownloadService
import jakarta.servlet.http.HttpServletResponse
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/download")
class DownloadController(
    private val downloadService: DownloadService,
) {
    @GetMapping("/large")
    fun large(
        @RequestParam(defaultValue = "1024") sizeKb: Int,
        response: HttpServletResponse,
    ) {
        downloadService.streamLarge(sizeKb, response)
    }
}
```

- [ ] **Step 5: 테스트 재실행**

Run:
```bash
./gradlew test --tests "com.example.buggy.controller.DownloadControllerTest"
```

Expected: PASS (1 test)

- [ ] **Step 6: Commit + tag**

```bash
cd ~/dev/demo-buggy-service
git add src/main/kotlin/com/example/buggy/controller/DownloadController.kt \
        src/main/kotlin/com/example/buggy/service/DownloadService.kt \
        src/test/kotlin/com/example/buggy/controller/DownloadControllerTest.kt
git commit -m "feat(scenario-6): DownloadController streams large response — broken pipe on client disconnect"
git tag scenario-6
git push --tags
git push
```

---

## Task 6: 시나리오 6 k6 스크립트

**Files:**
- Create: `$REPO/infra/loadgen/k6/scenario-6-benign.js`

- [ ] **Step 1: k6 스크립트 작성**

Create `$REPO/infra/loadgen/k6/scenario-6-benign.js`:

```javascript
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
    // 큰 파일 + 매우 짧은 timeout → 서버가 streaming 중 클라이언트 끊김
    http.get(`${BASE}/api/download/large?sizeKb=10240`, {
        timeout: '100ms',  // 의도적으로 짧게 — broken pipe 유도
    });
    sleep(0.3);
}
```

- [ ] **Step 2: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add infra/loadgen/k6/scenario-6-benign.js
git commit -m "feat(loadgen): scenario-6 k6 — large download with 100ms timeout to trigger ClientAbortException"
```

---

## Task 7: ai-bot 자체 Grafana 대시보드

**Files:**
- Create: `$REPO/infra/grafana/dashboards/ai-bot-overview.json`

ai-bot은 stdout에 JSON 로그를 출력하므로 (Python logging.basicConfig는 plain text지만, Alloy가 컨테이너 로그 수집), 다음 메트릭들을 LogQL로 집계할 수 있다. 단 ai-bot은 logging.basicConfig를 plain text 포맷으로 쓰므로, **Plan 4에서 ai-bot 로깅 포맷을 JSON으로 변경**한다.

- [ ] **Step 1: ai-bot 로깅을 JSON 포맷으로 변경**

`ai-bot/src/ai_bot/main.py`의 logging.basicConfig를 다음으로 교체:

```python
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key in ("service", "category", "incident_id", "run_id", "confidence", "cost_usd"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_setup_logging()
logger = logging.getLogger(__name__)
```

기존 `logging.basicConfig(...)` 호출은 제거.

- [ ] **Step 2: Alloy가 ai-bot 컨테이너도 수집하도록 확장**

`infra/alloy/alloy.hcl`의 `keep` regex 확인 — 현재 `/(app|buggy-service|demo-app-.*)`. `ai-bot`도 추가:

기존:
```hcl
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(app|buggy-service|demo-app-.*)"
    action        = "keep"
  }
```

변경:
```hcl
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(app|buggy-service|ai-bot|demo-app-.*)"
    action        = "keep"
  }
```

또한 service 라벨 매핑 rule 추가:

기존 service 라벨 rule들 아래에 추가:
```hcl
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/ai-bot"
    target_label  = "service"
    replacement   = "ai-bot"
  }
```

- [ ] **Step 3: ai-bot-overview.json 대시보드 작성**

Create `infra/grafana/dashboards/ai-bot-overview.json`:

```json
{
  "annotations": {"list": []},
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "type": "stat",
      "title": "Total Analysis Runs (last 1h)",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
      "targets": [
        {
          "expr": "sum(count_over_time({service=\"ai-bot\"} | json | message=~\"finding recorded.*\" [1h]))",
          "refId": "A"
        }
      ],
      "options": {"colorMode": "value", "graphMode": "none", "textMode": "value"}
    },
    {
      "type": "stat",
      "title": "Failed Runs (last 1h)",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
      "targets": [
        {
          "expr": "sum(count_over_time({service=\"ai-bot\"} | json | message=~\".*orchestrator error.*\" [1h]))",
          "refId": "A"
        }
      ],
      "options": {"colorMode": "value", "graphMode": "none", "textMode": "value"},
      "fieldConfig": {
        "defaults": {
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "green", "value": null}, {"color": "red", "value": 1}]
          }
        }
      }
    },
    {
      "type": "timeseries",
      "title": "Runs over time (by category)",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "targets": [
        {
          "expr": "sum by (category) (count_over_time({service=\"ai-bot\"} | json | category=~\".+\" [5m]))",
          "refId": "A",
          "legendFormat": "{{category}}"
        }
      ]
    },
    {
      "type": "bargauge",
      "title": "Category distribution (last 24h)",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "targets": [
        {
          "expr": "sum by (category) (count_over_time({service=\"ai-bot\"} | json | category=~\".+\" [24h]))",
          "refId": "A",
          "legendFormat": "{{category}}"
        }
      ]
    },
    {
      "type": "logs",
      "title": "Recent Analysis Runs",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 10, "w": 24, "x": 0, "y": 16},
      "targets": [
        {
          "expr": "{service=\"ai-bot\"} | json | level=~\"INFO|ERROR\"",
          "refId": "A"
        }
      ],
      "options": {"showTime": true, "sortOrder": "Descending", "wrapLogMessage": true}
    }
  ],
  "refresh": "30s",
  "schemaVersion": 39,
  "tags": ["ai-bot"],
  "templating": {"list": []},
  "time": {"from": "now-1h", "to": "now"},
  "title": "AI Bot Overview",
  "uid": "ai-bot-overview",
  "version": 1,
  "weekStart": ""
}
```

- [ ] **Step 4: 풀세트 기동 + 대시보드 확인**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo down -v
docker compose --profile demo up -d --build
sleep 90
open http://localhost:3000  # admin/admin
```

Grafana → Dashboards → AI Bot Overview 클릭. 시나리오 1 트리거 후 패널들에 데이터 반영 확인.

- [ ] **Step 5: Commit**

```bash
git add ai-bot/src/ai_bot/main.py infra/alloy/alloy.hcl \
        infra/grafana/dashboards/ai-bot-overview.json
git commit -m "feat(grafana): AI Bot Overview dashboard + JSON logging + Alloy ai-bot collection"
```

---

## Task 8: DEMO_GUIDE.md

**Files:**
- Create: `$REPO/docs/DEMO_GUIDE.md`

- [ ] **Step 1: 작성**

Create `$REPO/docs/DEMO_GUIDE.md`:

```markdown
# Demo Guide

이 문서는 다른 사람에게 (또는 면접관에게) 데모를 시연하기 위한 체크리스트.

---

## 0. 사전 준비 (1회)

### 환경변수 (`~/.../demo-log-observability/.env`)
```bash
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO=kiekk/demo-buggy-service
GITHUB_REPO_URL=https://github.com/kiekk/demo-buggy-service.git
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
WEBHOOK_TOKEN=$(openssl rand -hex 16)
AI_BOT_WEBHOOK_URL=http://ai-bot:8090/webhooks/grafana
HIKARI_MAX_POOL=10
DRY_RUN=false
DAILY_COST_CAP_USD=5
```

### 외부 셋업
- demo-buggy-service GitHub 레포 + main 브랜치 protection (require PR review)
- Slack 채널 `#ai-bot-demo` + Incoming Webhook

### 의존성
- Docker 20.10+, Docker Compose v2
- Node.js 20+ (Claude Code CLI 의존성, ai-bot 이미지가 자동 설치)

---

## 1. 풀세트 기동 (시연 직전)

```bash
cd ~/.../demo-log-observability
git submodule update --init --recursive
docker compose --profile demo down -v   # 깨끗하게 시작
docker compose --profile demo up -d --build
sleep 90   # buggy-service Flyway 마이그레이션 + ai-bot 초기화 대기
```

### 확인 (모두 OK여야 함)
```bash
docker compose ps                      # 모든 서비스 Up
curl http://localhost:8090/health      # ai-bot {"status":"ok",...}
curl http://localhost:8081/actuator/health   # buggy-service UP
open http://localhost:3000             # Grafana (admin/admin)
```

Grafana → Dashboards → "AI Bot Overview" / "App Logs Overview" 패널 확인.

---

## 2. 시나리오 시연

각 시나리오는 약 3분 (k6 90초 + alert 평가 30초 + LLM 분석 1~2분).

### 시연 흐름 (모든 시나리오 공통)

1. 트리거 명령 실행
2. Grafana Explore에서 LogQL로 에러 발생 확인 — `{service="demo-buggy-service"} | json | level="ERROR"`
3. 90~120초 후 Slack 채널에서 `🚨 → 🔍 → ✅/🔎/⚙️/🔇` 메시지 흐름 확인
4. GitHub에서 Issue/PR 생성 확인
5. (시간 있으면) Grafana "AI Bot Overview"에서 카테고리 분포 변화 확인

### 시나리오 1 — CODE_BUG (NPE)

```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
```

**기대 결과**:
- Slack `✅ PR 생성됨 — NullPointerException...`
- GitHub: Draft PR with null check 추가

### 시나리오 2 — CODE_BUG (0 나눗셈)

```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-2-divzero.js
```

**기대 결과**: Slack `✅ PR 생성됨 — ArithmeticException`, PR에 `if (items == 0) ...` 가드

### 시나리오 3 — CODE_BUG (Enum 매핑)

```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-3-enum.js
```

**기대 결과**: Slack `✅ PR 생성됨 — IllegalArgumentException`, PR에 try-catch 또는 화이트리스트

### 시나리오 4 — DATA_ANOMALY (빈 city)

```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-4-data.js
```

**기대 결과**:
- Slack `🔎 데이터 조사 필요 — IllegalArgumentException`
- GitHub Issue **only** (PR 없음), 본문에 검증 SQL 3개 + LogQL 2개

### 시나리오 5 — INFRA_ISSUE (HikariCP 풀)

```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-5-dbpool.js
```

**기대 결과**:
- Slack `⚙️ 인프라 점검 필요 — SQLTransientConnectionException`
- GitHub Issue **only**, 본문에 점검 체크리스트

### 시나리오 6 — BENIGN_ERROR (broken pipe)

```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-6-benign.js
```

**기대 결과**:
- Slack `🔇 노이즈 에러 처리 PR 생성됨`
- GitHub: 좁은 범위 PR (ExceptionHandler 추가) + 별도 Issue (alert rule 조정 제안)

---

## 3. 시연 후 정리

### 비용 확인
```bash
docker compose exec ai-bot sqlite3 /data/ai-bot.db \
    "SELECT date(created_at), SUM(cost_usd), SUM(input_tokens), SUM(output_tokens) FROM llm_usage GROUP BY date(created_at);"
```

### 정리
```bash
docker compose --profile demo down
# 데이터까지 완전 정리하려면 -v 추가
# docker compose --profile demo down -v
```

### Draft PR 처리
- 시연용 PR은 머지하지 말 것 (의도적 버그 보존)
- 다음 시연 전에 GitHub에서 일괄 close (재사용은 안 됨 — dedup이 같은 fingerprint를 막아서)
- 또는 ai-bot SQLite를 비우면 dedup 초기화: `docker compose exec ai-bot rm /data/ai-bot.db && docker compose restart ai-bot`

---

## 4. 시연 중 자주 묻는 질문 (FAQ)

**Q. AI가 잘못 고치면?**
- A. PR은 항상 Draft + `human-review-required` 라벨. 사람이 검토 후 머지. 자동 머지 금지.

**Q. 비용이 폭주하면?**
- A. 일일 cap (`DAILY_COST_CAP_USD=5`). 초과 시 신규 분석 자동 거절 + Slack 경고.

**Q. 알림이 자기 자신을 무한 트리거하지 않나?**
- A. dedup 윈도우 (`DEDUP_WINDOW_MINUTES=10`)로 같은 fingerprint 10분 내 1회만 분석. BENIGN_ERROR는 24시간 cooldown.

**Q. 회사 운영 환경에 그대로 도입 가능?**
- A. 데모 단순화 vs 회사 기획서 차이 있음 (Kafka MSK 미사용, GitHub Issue를 Jira로 교체 필요, Anthropic API key를 Bedrock로 교체 등). spec 문서 참고.

---

## 5. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| ai-bot이 webhook 받았는데 분석 시작 안 함 | dedup이 동일 fingerprint 차단 중 | 10분 대기 또는 SQLite 비우기 |
| Claude 분석이 INSUFFICIENT_CONTEXT만 반환 | system prompt 가이드 부족 또는 코드 컨텍스트 부족 | `ANTHROPIC_API_KEY` 확인 + 로그에 도구 호출 흐름 확인 |
| PR 생성 실패 | GITHUB_TOKEN 권한 부족 | repo scope 전체 + main branch protection은 PR review만 require (직접 push 금지 X) |
| Slack 알림 안 옴 | SLACK_WEBHOOK_URL 잘못됨 | `curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"test"}'` 검증 |
| Alloy가 ai-bot 로그 수집 안 함 | alloy.hcl keep regex 미반영 | `docker compose restart alloy` |
| Grafana에 ai-bot 패널 비어있음 | Loki 인덱싱 지연 또는 service 라벨 누락 | Grafana Explore에서 `{service="ai-bot"}` 쿼리로 직접 확인 |

---

## 6. 시연 시간 예산

| 단계 | 시간 |
|---|---|
| 배경 설명 (spec 요약) | 3분 |
| 풀세트 기동 + Grafana 한 바퀴 | 3분 |
| 시나리오 1~3 (CODE_BUG, 빠른 시연) | 각 2분 × 3 = 6분 |
| 시나리오 4 (DATA_ANOMALY, 차별화 강조) | 4분 |
| 시나리오 5 (INFRA_ISSUE) | 3분 |
| 시나리오 6 (BENIGN_ERROR, 클로징) | 3분 |
| Q&A | 5분 |
| **합계** | **~27분** |

빠른 버전 (10분): 시나리오 1 + 4 + 6만 시연.
```

- [ ] **Step 2: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add docs/DEMO_GUIDE.md
git commit -m "docs: DEMO_GUIDE with scenario checklist + FAQ + troubleshooting"
```

---

## Task 9: ARCHITECTURE.md

**Files:**
- Create: `$REPO/docs/ARCHITECTURE.md`

이 문서는 spec의 핵심을 간략하게 압축한 "시연자가 면접 5분 안에 보여줄 수 있는" 다이어그램 + 한 문단 설명.

- [ ] **Step 1: 작성**

Create `$REPO/docs/ARCHITECTURE.md`:

```markdown
# Architecture

> 자세한 설계는 [spec](superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md). 이 문서는 5분 설명용 요약.

## 한 줄 요약

Grafana Alert → ai-bot이 webhook 수신 → 배포된 commit SHA의 코드를 worktree로 마운트 → Claude Agent SDK가 도구로 코드를 탐색 → 5개 카테고리 중 하나로 분류 → 카테고리에 맞는 GitHub Issue + Draft PR 자동 생성 + Slack 알림.

## 다이어그램

```
demo-buggy-service (의도적 버그 6종)
  ↓ JSON 로그 (commit_sha MDC)
Alloy → Loki → Grafana (Alert rule)
                         ↓ Webhook (Bearer auth)
                       ai-bot (Python/FastAPI)
                         ├─ dedup (10분)
                         ├─ cost cap ($5/일)
                         ├─ LogFetcher (Loki HTTP)
                         ├─ RepoManager (git worktree at commit_sha)
                         ├─ Claude Agent SDK ─── 도구 7종
                         │                          ├─ read_file
                         │                          ├─ grep
                         │                          ├─ git_log / git_diff
                         │                          ├─ read_db_schema
                         │                          ├─ propose_patch (≤30라인)
                         │                          └─ report_finding (final)
                         ├─ GitHubClient (Issue/Draft PR)
                         └─ SlackNotifier
                              ↓
                         Slack #ai-bot-demo
```

## 5개 카테고리 → 봇 동작

| 카테고리 | 봇 동작 |
|---|---|
| CODE_BUG | Issue + Draft PR (코드 패치) |
| BENIGN_ERROR | Issue + Draft PR (ExceptionHandler) + 별도 alert rule 제안 Issue |
| DATA_ANOMALY | Issue만 (SQL + LogQL 검증 쿼리 첨부, PR 없음) |
| INFRA_ISSUE | Issue만 (점검 체크리스트) |
| INSUFFICIENT_CONTEXT | Issue만 (확인 필요 안내) |

## 안전장치 (12종 중 핵심)

- **PR은 항상 Draft** + `human-review-required` 라벨
- **confidence ≥ 0.7**만 PR 생성
- **dedup 10분 윈도우** (같은 fingerprint 무한 분석 차단)
- **BENIGN_ERROR 24시간 cooldown** (오판 시 PR 폭주 방지)
- **alert rule 자동 수정 금지** (가장 위험한 self-improving loop 차단)
- **수정 범위**: 단일 파일 + 30라인 이하
- **Allowlist 디렉토리**: `src/main/`, `src/test/`, `src/main/resources/db/migration/` 외 접근 차단
- **일일 LLM 비용 cap**: 기본 $5
- **Dry-run 모드**: GitHub/Slack 호출을 콘솔로 대체
- **Webhook Bearer 토큰** 검증

## 데모와 회사 기획서의 차이

| 항목 | 회사 기획서 | 데모 |
|---|---|---|
| 메시지 브로커 | Kafka MSK | 없음 (직접 HTTP) |
| 이슈 트래커 | Jira | GitHub Issue |
| Git 호스팅 | GitLab self-host | GitHub |
| 로그 저장소 | CloudWatch | Loki |
| LLM 통합 | anthropic SDK 직접 호출 + 직접 컨텍스트 조립 | Claude Agent SDK (자율 도구 사용) |

회사 환경 도입 시 위 항목들을 단계적으로 교체. spec 16장 참고.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: 5-minute ARCHITECTURE summary"
```

---

## Task 10: README 최종화

**Files:**
- Modify: `$REPO/README.md`

- [ ] **Step 1: README에 데모 진입점 명시**

기존 README의 "AI Incident Bot 데모" 섹션을 다음으로 교체:

```markdown
## AI Incident Bot 데모

모니터링 알림 → AI가 배포된 코드를 분석 → GitHub에 Issue/PR 자동 생성하는 전체 파이프라인 데모.

### 5분 안에 시작
1. `.env` 셋업: [`docs/DEMO_GUIDE.md` § 0](docs/DEMO_GUIDE.md#0-사전-준비-1회) 참고
2. `git submodule update --init --recursive`
3. `docker compose --profile demo up -d --build`
4. 90초 후: 시나리오 트리거

### 문서
- [DEMO_GUIDE](docs/DEMO_GUIDE.md) — 시나리오별 시연 체크리스트
- [ARCHITECTURE](docs/ARCHITECTURE.md) — 5분 설명용 요약
- [spec](docs/superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md) — 전체 설계 문서
- [plans](docs/superpowers/plans/) — 구현 plan 1~4

### 시연 시나리오 6개
| # | 카테고리 | 트리거 |
|---|---|---|
| 1 | CODE_BUG (NPE) | `scenario-1-npe.js` |
| 2 | CODE_BUG (0 나눗셈) | `scenario-2-divzero.js` |
| 3 | CODE_BUG (Enum) | `scenario-3-enum.js` |
| 4 | DATA_ANOMALY | `scenario-4-data.js` |
| 5 | INFRA_ISSUE | `scenario-5-dbpool.js` |
| 6 | BENIGN_ERROR | `scenario-6-benign.js` |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: finalize README with demo entrypoint + scenario table"
```

---

## Task 11: End-to-end Plan 4 검증 (모든 시나리오)

- [ ] **Step 1: 풀세트 기동**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo down -v
docker compose --profile demo up -d --build
sleep 120
```

- [ ] **Step 2: 시나리오 1~6 순차 트리거 + 검증**

각 시나리오 사이에 3분 간격. 트리거 후 Slack/GitHub 확인.

```bash
for s in 1-npe 2-divzero 3-enum 4-data 5-dbpool 6-benign; do
    echo "=== scenario-$s ==="
    docker compose --profile loadtest run --rm loadgen run /scripts/scenario-$s.js
    echo "Waiting 3 min for analysis to complete..."
    sleep 180
done
```

**Expected (Slack 메시지 순서)**:
- 시나리오 1: `🚨 ... → 🔍 ... → ✅ PR ...`
- 시나리오 2: 동일 패턴
- 시나리오 3: 동일 패턴
- 시나리오 4: `🚨 ... → 🔍 ... → 🔎 데이터 조사 필요 (PR 없음)`
- 시나리오 5: `🚨 ... → 🔍 ... → ⚙️ 인프라 점검 필요`
- 시나리오 6: `🚨 ... → 🔍 ... → 🔇 노이즈 에러 처리 PR ...`

**Expected (GitHub)**:
- 시나리오 1~3, 6: Issue + Draft PR
- 시나리오 4, 5: Issue only (PR 없음)
- 시나리오 6: 추가 Issue (alert rule 제안)

- [ ] **Step 3: DB 검증**

Run:
```bash
docker compose exec ai-bot sqlite3 /data/ai-bot.db \
    "SELECT category, COUNT(*), AVG(confidence) FROM analysis_runs WHERE status='COMPLETED' GROUP BY category;"
```

Expected: 5개 카테고리 모두 row 1+개 (또는 데모 흐름에 따라 일부 빈 카테고리는 OK)

- [ ] **Step 4: Grafana 대시보드 확인**

http://localhost:3000 → AI Bot Overview → 카테고리 분포 bargauge에 5개 카테고리 막대 확인.

- [ ] **Step 5: 비용 확인**

Run:
```bash
docker compose exec ai-bot sqlite3 /data/ai-bot.db \
    "SELECT date(created_at), SUM(cost_usd), COUNT(*) FROM llm_usage GROUP BY date(created_at);"
```

Expected: 6 시나리오 합산 $1.5 미만 (Sonnet 기준)

- [ ] **Step 6: 정리**

Run:
```bash
docker compose --profile demo down
```

- [ ] **Step 7: 최종 커밋**

이 task에서 변경된 파일은 없음. 검증만.

만약 시나리오 중 기대와 다른 카테고리로 분류된 게 있다면:
1. `ai-bot/src/ai_bot/analyzer/prompts.py`의 system prompt에 해당 케이스 가이드 강화
2. 다시 검증
3. 변경 사항 commit

---

## Plan 4 Out of Scope

- 멀티 프로바이더 (Bedrock/Vertex) 추상화
- Haiku 1차 분류 → Sonnet 심층 분석 라우팅
- Trace (Tempo) 연동
- GPT-4o fallback
- 실 운영 환경 보안 강화 (Vault, IRSA 등)
- Jira / Linear / GitLab 통합

---

## Plan 4 완료 시 산출물

- 시연 시나리오 6개 모두 동작 (5개 카테고리 분류 모두 시연 가능)
- ai-bot 자체 Grafana 대시보드 (run 통계, 카테고리 분포, recent logs)
- DEMO_GUIDE.md (5분/15분/30분 시연 스크립트)
- ARCHITECTURE.md (면접 설명용 요약)
- README가 데모 진입점으로 정리됨

---

## 전체 데모 완성 (Plan 1 + 2 + 3 + 4 종료 후)

`docker compose --profile demo up -d --build` 한 줄로:
- LGTM 관측성 스택
- Postgres + demo-buggy-service (시나리오 1~6 코드)
- ai-bot (Python/FastAPI/Claude Agent SDK/GitHub/Slack 통합)
- Grafana 2개 대시보드 (App Logs Overview, AI Bot Overview)

k6 시나리오 트리거 → 90~180초 후 Slack 알림 + GitHub Issue/PR 자동 생성.

회사(Waiker) 도입 시 spec 16장의 변환 가이드 참고 (Kafka, Jira, GitLab, Bedrock 교체).
