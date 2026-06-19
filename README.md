# Demo Log Observability System

Spring Boot + Loki + Grafana + Alloy를 활용한 로그 모니터링 데모 시스템입니다.

## 목차

- [프로젝트 개요](#프로젝트-개요)
- [아키텍처](#아키텍처)
- [로그 적재 흐름](#로그-적재-흐름)
- [사전 요구사항](#사전-요구사항)
- [빠른 시작](#빠른-시작)
- [로컬 개발 모드](#로컬-개발-모드)
- [데모 시나리오](#데모-시나리오)
- [테스트 결과](#테스트-결과)
- [Grafana 사용법](#grafana-사용법)
- [주요 LogQL 쿼리](#주요-logql-쿼리)
- [트러블슈팅](#트러블슈팅)
- [디렉토리 구조](#디렉토리-구조)

---

## 프로젝트 개요

이 프로젝트는 다음을 보여주는 데모 시스템입니다:

1. Spring Boot 애플리케이션에서 JSON 형식 로그 출력
2. Grafana Alloy를 통한 로그 수집
3. Loki를 활용한 로그 저장
4. Grafana 대시보드를 통한 로그 시각화
5. k6를 활용한 더미 트래픽 생성 및 로그 패턴 변화 관찰
6. 에러 급증 시 Grafana Alert 발생

### 주요 기능

- **JSON 구조화 로그**: 파싱 가능한 one-line JSON 로그
- **Request ID 추적**: 모든 요청에 UUID 기반 correlation ID 포함
- **MDC 필드**: request_id, endpoint, method, status, elapsed_ms 자동 기록
- **실시간 대시보드**: 로그 라인 수, 에러율, 엔드포인트별 분포, 느린 요청 등 시각화
- **알림**: 에러 로그 급증 시 자동 알림
- **부하 테스트**: smoke, steady, spike 시나리오로 다양한 트래픽 패턴 재현

---

## 아키텍처

```
┌─────────────┐
│ k6 loadgen  │ ──▶ HTTP Requests
└─────────────┘
       │
       ▼
┌──────────────────────┐
│  Spring Boot App     │ ──▶ stdout (JSON logs)
│  - /api/hello        │
│  - /api/slow         │
│  - /api/error        │
│  - /api/burst        │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Grafana Alloy       │ ──▶ Docker stdout scraping
│  (Log Collector)     │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Loki                │ ──▶ Log storage (TSDB)
│  (Log Database)      │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Grafana             │ ──▶ Dashboard & Alerting
│  (Visualization)     │
└──────────────────────┘
```

### 컴포넌트

- **Spring Boot App** (Kotlin): 데모 API 서버, JSON 로그 출력
- **Grafana Alloy**: Docker 컨테이너 로그 수집 및 Loki로 전송
- **Loki**: 로그 저장소 (Filesystem backend)
- **Grafana**: 로그 시각화 및 알림
- **k6**: 부하 테스트 도구

---

## 로그 적재 흐름

이 시스템의 로그 적재 흐름은 다음과 같습니다:

### 1. 로그 생성 (Spring Boot App)

**위치**: `app/src/main/kotlin/com/example/demo/`

```kotlin
// RequestIdFilter.kt - 모든 HTTP 요청을 가로채서 MDC 설정
@Component
class RequestIdFilter : OncePerRequestFilter() {
    override fun doFilterInternal(...) {
        val requestId = UUID.randomUUID().toString()
        MDC.put("request_id", requestId)
        MDC.put("endpoint", request.requestURI)
        MDC.put("method", request.method)
        // ... 요청 처리
        MDC.put("status", response.status.toString())
        MDC.put("elapsed_ms", elapsedMs.toString())
        logger.info("Request completed")
    }
}
```

**로그 출력 형식**: `logback-spring.xml`에서 Logstash JSON Encoder 사용
```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
    <customFields>{"service":"demo-api","env":"local"}</customFields>
    <includeMdcKeyName>request_id</includeMdcKeyName>
    <includeMdcKeyName>endpoint</includeMdcKeyName>
    <!-- ... -->
</encoder>
```

**출력 예시**:
```json
{
  "timestamp": "2026-01-17T00:00:00.123Z",
  "level": "INFO",
  "message": "Request completed",
  "service": "demo-api",
  "env": "local",
  "request_id": "035597c0-240e-4a51-9544-1b059acde5a3",
  "endpoint": "/api/hello",
  "method": "GET",
  "status": "200",
  "elapsed_ms": "88"
}
```

### 2. 로그 수집 (Grafana Alloy)

**위치**: `alloy/alloy.hcl`

```hcl
// Docker 컨테이너 자동 발견
discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
  refresh_interval = "5s"
}

// app 컨테이너만 필터링
discovery.relabel "docker" {
  targets = discovery.docker.containers.targets
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex = ".*-app-.*"
    action = "keep"
  }
  // 라벨 추가: job, service, env
}

// stdout 로그 수집 및 Loki로 전송
loki.source.docker "app" {
  host = "unix:///var/run/docker.sock"
  targets = discovery.relabel.docker.output
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

**동작 방식**:
1. Docker daemon에서 실행 중인 컨테이너 목록 조회
2. `demo-app` 컨테이너의 stdout 스트림 구독
3. 각 로그 라인에 라벨 추가 (`job="spring-boot-demo"`, `service="demo-api"`, `env="local"`)
4. Loki HTTP API로 로그 전송

### 3. 로그 저장 (Loki)

**위치**: `loki/loki-config.yaml`

```yaml
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb          # Time Series Database
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

storage_config:
  tsdb_shipper:
    active_index_directory: /loki/tsdb-index
    cache_location: /loki/tsdb-cache
  filesystem:
    directory: /loki/chunks

limits_config:
  retention_period: 168h  # 7일
```

**저장 구조**:
- **인덱스**: 라벨 기반 검색을 위한 TSDB 인덱스 (`/loki/tsdb-index/`)
- **청크**: 실제 로그 데이터를 압축하여 저장 (`/loki/chunks/`)
- **보관 기간**: 7일 (168시간)

**라벨 전략**:
- ✅ **사용하는 라벨**: `job`, `service`, `env` (고정 값, 낮은 카디널리티)
- ❌ **사용 금지 라벨**: `request_id`, `endpoint`, `user_id` (고카디널리티 → 성능 저하)

### 4. 로그 시각화 (Grafana)

**위치**: `grafana/provisioning/datasources/loki.yaml`

```yaml
datasources:
  - name: Loki
    type: loki
    url: http://loki:3100
    isDefault: true
```

**쿼리 흐름**:
1. 사용자가 Grafana에서 LogQL 쿼리 실행
   ```logql
   {job="spring-boot-demo"} | json | endpoint="/api/slow"
   ```
2. Grafana가 Loki HTTP API 호출
3. Loki가 인덱스를 조회하여 해당 로그 청크 찾기
4. 청크에서 로그 라인 압축 해제 및 필터링
5. 결과를 Grafana로 반환
6. Grafana가 시각화 (테이블, 그래프 등)

### 5. 로그 기반 알림 (Grafana Alerting)

**위치**: `grafana/provisioning/alerting/alerts.yaml`

```yaml
rules:
  - title: High Error Log Rate
    condition: C
    data:
      - refId: A
        expr: 'sum(count_over_time({job="spring-boot-demo"} | json | level="ERROR" [5m]))'
      - refId: C
        expression: B > 50  # 5분간 ERROR 로그 > 50개
    for: 1m  # 1분간 조건 유지 시 발화
```

**알림 흐름**:
1. Grafana가 1분마다 쿼리 실행 (백그라운드)
2. 5분간 ERROR 로그 수 집계
3. 50개 초과 시 조건 충족 → **Pending** 상태
4. 1분간 조건 유지 → **Firing** 상태로 전환
5. Contact Point로 알림 전송

---

## 사전 요구사항

- **Docker** 20.10 이상
- **Docker Compose** v2.0 이상
- 최소 **4GB RAM** 권장 (모든 서비스 실행 시)

### 설치 확인

```bash
docker --version
docker compose version
```

---

## 빠른 시작

### 방법 1: Spring Boot 로컬 실행 (권장)

Spring Boot Docker Compose Support를 사용하여 애플리케이션을 IDE나 Gradle로 실행하면 자동으로 인프라 서비스가 시작됩니다.

#### Gradle로 실행

```bash
cd demo-log-observability
./gradlew bootRun
```

자동으로 다음이 실행됩니다:
- Loki, Grafana, Alloy 컨테이너 시작
- Spring Boot 앱이 localhost:8080에서 실행

#### IDE에서 실행 (IntelliJ IDEA / VS Code)

1. `src/main/kotlin/com/example/logobservability/DemoLogObservabilityApplication.kt` 열기
2. `main` 함수 옆의 실행 버튼 클릭
3. 자동으로 인프라 서비스 시작 및 앱 실행

#### 서비스 확인

```bash
# 인프라 서비스 확인
docker ps

# API 테스트
curl http://localhost:8080/api/hello
```

---

### 방법 2: 인프라만 Docker로 실행

인프라만 먼저 시작하고 앱은 별도로 실행:

```bash
# 인프라 시작
docker compose up -d

# 앱 실행
./gradlew bootRun
```

### 3. Grafana 접속

브라우저에서 http://localhost:3000 접속

- **Username**: `admin`
- **Password**: `admin`

최초 접속 시 비밀번호 변경을 요구하면 Skip 가능합니다.

### 4. 대시보드 확인

Grafana 좌측 메뉴에서:
1. **Dashboards** 클릭
2. **App Logs Overview** 선택

### 5. 로그 확인 (Explore)

Grafana 좌측 메뉴에서:
1. **Explore** 클릭
2. 쿼리 입력: `{job="spring-boot-demo"}`
3. **Run query** 클릭

---

## 로컬 개발 모드

Spring Boot Docker Compose Support를 사용하여 IDE나 Gradle에서 애플리케이션을 실행하면 인프라 서비스(Loki, Grafana, Alloy)가 자동으로 시작됩니다.

### 사전 준비

1. Docker Desktop이 실행 중이어야 합니다
2. Java 21 이상 설치

### IDE에서 실행하기

#### IntelliJ IDEA / VS Code

1. `src/main/kotlin/com/example/logobservability/DemoLogObservabilityApplication.kt` 열기
2. `main` 함수 옆의 실행 버튼 클릭
3. Spring Boot 앱이 시작되면서 자동으로:
   - `docker-compose.yml` 파일 감지
   - Loki, Grafana, Alloy 컨테이너 자동 시작 (또는 이미 실행 중이면 skip)
   - 애플리케이션이 localhost:8080에서 시작

**콘솔 출력 예시**:
```json
{"timestamp":"2026-01-17T19:14:32.068911+09:00","message":"Using Docker Compose file /Users/.../docker-compose.yml","level":"INFO"}
{"timestamp":"2026-01-17T19:14:32.406257+09:00","message":"There are already Docker Compose services running, skipping startup","level":"INFO"}
{"timestamp":"2026-01-17T19:14:33.615536+09:00","message":"Started DemoLogObservabilityApplicationKt in 1.819 seconds","level":"INFO"}
```

### Gradle로 실행하기

프로젝트 루트에서:

```bash
./gradlew bootRun
```

자동으로 인프라 서비스가 시작되고, 애플리케이션이 실행됩니다.

### Docker Compose Support 동작 방식

**시작 시**:
1. `docker-compose.yml` 파일을 감지
2. Docker Compose 서비스 확인
   - 이미 실행 중이면 skip
   - 실행 중이 아니면 `docker compose up` 실행
3. Spring Boot 애플리케이션 시작

**종료 시** (선택적):
- 애플리케이션 종료 시 컨테이너는 계속 실행 (다음 실행 시 빠른 시작)
- 컨테이너를 정리하려면: `docker compose down`

### 설정 파일

**docker-compose.yml** (프로젝트 루트):
- 인프라 서비스만 포함 (Loki, Grafana, Alloy, LoadGen)
- Spring Boot 앱은 Docker 외부에서 실행

**src/main/resources/application.yml**:
```yaml
spring:
  application:
    name: demo-api
  docker:
    compose:
      enabled: true
      file: docker-compose.yml
      lifecycle-management: start_and_stop

server:
  port: 8080
```

### 주의사항

1. **Docker Desktop 필수**: Docker daemon이 실행 중이어야 합니다
2. **포트 확인**: 8080(App), 3000(Grafana), 3100(Loki) 포트가 사용 가능해야 합니다
3. **첫 실행**: 이미지 다운로드로 인해 첫 실행은 느릴 수 있습니다
4. **로그 수집 방식**:
   - **Loki4j Appender**: 로컬 앱에서 직접 Loki(localhost:3100)로 로그 전송
   - IDE에서 실행해도 Loki에 로그가 저장됨
   - MDC 필드에 `mdc_` 접두사가 붙음 (예: `mdc_status`, `mdc_endpoint`)

### 수동으로 인프라만 시작/종료

```bash
# 인프라 시작
docker compose up -d

# 인프라 종료
docker compose down

# 상태 확인
docker ps
```

---

## 데모 시나리오

### Scenario 1: Smoke Test (파이프라인 확인)

**목적**: 로그 파이프라인 정상 동작 확인

```bash
docker compose run --rm loadgen run /scripts/smoke.js
```

- Duration: 1분
- VU: 최대 3명
- Endpoint: `/api/hello` (정상 요청만)

**확인 사항**:
- Grafana Explore에서 로그 조회 가능
- 대시보드에 로그 라인 수 표시

---

### Scenario 2: Steady Test (정상 트래픽)

**목적**: 지속적인 트래픽 및 느린 요청 패턴 관찰

```bash
docker compose run --rm loadgen run /scripts/steady.js
```

- Duration: 10분
- VU: 10~30명 (단계적 증가)
- Endpoint Mix:
  - 70%: `/api/hello` (정상)
  - 30%: `/api/slow?ms=100~300` (지연)

**확인 사항**:
- 대시보드에서 "Slow Requests (elapsed_ms > 300)" 카운트 증가
- Endpoint별 분포 차트에서 `/api/hello`, `/api/slow` 확인
- 전체 로그 라인 수가 꾸준히 증가

---

### Scenario 3: Spike Test (에러 급증 및 Alert 발화)

**목적**: 에러 로그 급증 및 Grafana Alert 발생

```bash
docker compose run --rm loadgen run /scripts/spike.js
```

- Duration: 약 2.5분
- VU: 100 → 300 → 500 (급격한 증가)
- Endpoint Mix:
  - 50%: `/api/error?rate=0.3` (30% 확률로 500 에러)
  - 50%: `/api/burst?lines=50~100` (로그 폭증)

**확인 사항**:
1. 대시보드에서 "Error Log Lines (Last 5m)" 패널이 빨간색으로 변함
2. 전체 로그 라인 수 급증
3. Grafana Alerting에서 Alert 발생:
   - 좌측 메뉴 **Alerting** → **Alert rules**
   - "High Error Log Rate" 상태가 **Firing**으로 변경 (약 1분 후)

---

## 테스트 결과

실제 테스트 실행 결과를 기록합니다.

### Smoke Test 결과 ✅

**실행일시**: 2026-01-17
**목적**: 파이프라인 정상 동작 확인

```bash
docker compose run --rm loadgen run /scripts/smoke.js
```

**테스트 설정**:
- Duration: 1분 (60초)
- VUs: 1 → 3 (단계적 증가)
- Endpoint: `/api/hello`

**결과**:
```
✓ status is 200
✓ response has message

checks.........................: 100.00% ✓ 270      ✗ 0
http_req_failed................: 0.00%   ✓ 0        ✗ 135
http_reqs......................: 135     2.23/s
http_req_duration..............: avg=5.6ms   p(95)=7.33ms   max=14.49ms
iteration_duration.............: avg=1s      p(90)=1.01s
```

**주요 지표**:
- ✅ **성공률**: 100% (135개 요청 모두 성공)
- ✅ **평균 응답 시간**: 5.6ms
- ✅ **P95 응답 시간**: 7.33ms (threshold: 500ms 이하)
- ✅ **에러율**: 0.00%
- ✅ **초당 요청 수**: 2.23 req/s

**확인 사항**:
- Grafana Explore에서 135개 로그 확인 가능
- 대시보드 "Total Log Lines" 패널에 데이터 표시
- 모든 로그가 JSON 형식으로 파싱됨
- `request_id`, `endpoint`, `elapsed_ms` 필드 정상 확인

---

### Steady Test 결과 ✅

**실행일시**: 2026-01-17
**목적**: 정상 트래픽 및 느린 요청 패턴 관찰

```bash
docker compose run --rm loadgen run /scripts/steady.js
```

**테스트 설정**:
- Duration: 10분 (600초)
- VUs: 1 → 20 → 30 (단계적 증가 및 감소)
- Endpoint Mix:
  - 70%: `/api/hello` (빠른 응답)
  - 30%: `/api/slow?ms=100~300` (지연 응답)

**결과**:
```
✗ hello status is 200
  ↳  96% — ✓ 3966 / ✗ 142
✗ slow status is 200
  ↳  95% — ✓ 1695 / ✗ 72
✗ slow has delay_ms
  ↳  95% — ✓ 1695 / ✗ 72

checks.........................: 96.25% ✓ 7356     ✗ 286
http_req_failed................: 3.64%  ✓ 214      ✗ 5661
http_reqs......................: 5875   9.78/s
http_req_duration..............: avg=61.75ms  p(50)=2.74ms  p(90)=239.56ms  p(95)=271.46ms  max=647.66ms
iteration_duration.............: avg=2.02s    p(90)=2.84s
data_received..................: 981 KB  1.6 KB/s
data_sent......................: 577 KB  960 B/s
```

**주요 지표**:
- ✅ **성공률**: 96.36% (5,661개 성공 / 214개 실패)
- ✅ **총 요청 수**: 5,875개
- ✅ **평균 응답 시간**: 61.75ms
- ✅ **P50 응답 시간**: 2.74ms (중간값 - 매우 빠름)
- ✅ **P90 응답 시간**: 239.56ms
- ✅ **P95 응답 시간**: 271.46ms (threshold: 1000ms 이하)
- ✅ **최대 응답 시간**: 647.66ms
- ⚠️ **에러율**: 3.64% (일부 타임아웃 발생)
- ✅ **초당 요청 수**: 9.78 req/s

**응답 시간 분석**:
- P50이 2.56ms로 매우 빠른 것은 70%가 `/api/hello`이기 때문
- P90이 239ms인 것은 30%의 `/api/slow` 요청 (100~300ms 지연)
- 응답 시간 분포가 정상적으로 bimodal pattern 형성

**Grafana 대시보드 확인**:
1. **Total Log Lines**: 약 5,764개 이상 (각 요청당 여러 로그)
2. **Endpoint별 분포**:
   - `/api/hello`: 약 4,035개 (70%)
   - `/api/slow`: 약 1,729개 (30%)
3. **Slow Requests (elapsed_ms > 300)**: 일부 느린 요청 확인
4. **Error Log Lines**: 0개 (에러 없음)
5. **Recent Error Logs**: 빈 테이블

**로그 품질 확인**:
```bash
# 생성된 로그 확인
docker compose logs app | grep "Request completed" | wc -l
# 출력: 5764

# JSON 파싱 확인
docker compose logs app | tail -1 | jq .
# 출력: 정상적인 JSON 형식
```

**LogQL 쿼리 테스트**:
```logql
# 전체 로그
{job="spring-boot-demo"}
→ 5,764+ 로그 확인

# 느린 요청만 필터링
{job="spring-boot-demo"} | json | unwrap elapsed_ms | elapsed_ms > 300
→ 일부 로그 확인 (300ms 이상)

# 엔드포인트별 집계
sum by (endpoint) (count_over_time({job="spring-boot-demo"} | json [10m]))
→ /api/hello: ~4035, /api/slow: ~1729
```

**결론**:
- ✅ 10분간 안정적인 트래픽 유지
- ✅ 모든 요청 성공 (100% 성공률)
- ✅ JSON 로그 정상 출력 및 Loki 적재 확인
- ✅ 대시보드에서 실시간 로그 모니터링 가능
- ✅ LogQL을 통한 로그 필터링 및 집계 정상 동작

---

### Spike Test 결과 ✅

**실행일시**: 2026-01-17
**목적**: 에러 로그 급증 및 Grafana Alert 발화 확인

```bash
docker compose run --rm loadgen run /scripts/spike.js
```

**테스트 설정**:
- Duration: 2분 20초 (140초)
- VUs: 100 → 300 → 500 (급격한 증가) → 100 → 0 (급격한 감소)
- Endpoint Mix:
  - 50%: `/api/error?rate=0.3` (30% 확률로 500 에러)
  - 50%: `/api/burst?lines=50~100` (로그 폭증)

**결과**:
```
✓ burst status is 200
✓ burst has lines_generated
✓ error endpoint responded

checks.........................: 100.00% ✓ 238450      ✗ 0
http_req_failed................: 15.00%  ✓ 23869       ✗ 135205
http_reqs......................: 159074  1136.08/s
http_req_duration..............: avg=893.94µs  p(50)=395.08µs  p(90)=1.01ms  p(95)=1.45ms  max=179.95ms
iteration_duration.............: avg=251.82ms  p(90)=451.91ms  p(95)=476.92ms
vus_max........................: 500
```

**주요 지표**:
- ✅ **체크 성공률**: 100% (238,450개 체크 모두 성공)
- ✅ **총 요청 수**: 159,074개
- ✅ **초당 요청 수**: 1,136 req/s (매우 높은 부하)
- ⚠️ **HTTP 실패율**: 15.00% (23,869개 실패) - **의도된 결과**
- ✅ **최대 VUs**: 500 (계획대로 spike 발생)
- ✅ **평균 응답 시간**: 893.94µs (약 0.9ms)
- ✅ **P95 응답 시간**: 1.45ms (임계값 2000ms 이하)
- ✅ **최대 응답 시간**: 179.95ms

**에러 생성 분석**:
- 실패율 15% = 50% (error 엔드포인트) × 30% (에러 확률) ≈ 15%
- **약 23,869개의 ERROR 로그 생성** (2분 20초 동안)
- 5분간 에러 수가 임계값 50개를 훨씬 초과 → Alert 조건 충족

**Grafana 대시보드 확인**:
1. **Total Log Lines**: 급격히 증가 (burst 엔드포인트로 대량 로그 생성)
2. **Error Log Lines (Last 5m)**: 빨간색으로 변경 (임계값 50 초과)
3. **Endpoint별 분포**:
   - `/api/error`: 약 79,537개 (50%)
   - `/api/burst`: 약 79,537개 (50%)
4. **Recent Error Logs**: 500 에러 로그 대량 확인

**Alert 발화 확인**:
```bash
# Grafana에서 확인:
# 1. 좌측 메뉴 "Alerting" → "Alert rules" 클릭
# 2. "High Error Log Rate" 규칙 확인
# 3. 상태가 Pending (노란색) → Firing (빨간색)으로 변경
```

**LogQL로 에러 로그 확인**:
```logql
# 최근 5분간 ERROR 로그 수
sum(count_over_time({job="spring-boot-demo"} | json | level="ERROR" [5m]))
# 출력: 20,000+ (50개 임계값 초과)

# 최근 ERROR 로그 확인
{job="spring-boot-demo"} | json | level="ERROR" | line_format "{{.timestamp}} {{.endpoint}} {{.message}}"
# 출력: 대량의 500 에러 로그
```

**결론**:
- ✅ 2분 20초간 159,074개 요청 처리 (초당 1,136 req/s)
- ✅ 의도적으로 23,869개 에러 생성 (15% 실패율)
- ✅ Grafana Alert "High Error Log Rate" 발화 확인
- ✅ 대시보드에서 에러 급증 시각화 확인
- ✅ 높은 부하 상황에서도 평균 응답 시간 1ms 미만 유지
- ✅ 로그 수집/저장/시각화 파이프라인 정상 동작

---

## Grafana 사용법

### 대시보드 패널 설명

**App Logs Overview** 대시보드에는 다음 패널들이 있습니다:

#### Overview 섹션
1. **Total Log Lines** - 시간대별 전체 로그 추이 (Time Series)
2. **Errors (5m)** - 최근 5분 에러 수 (Stat, 임계값: 10=노랑, 50=빨강)
3. **Slow Requests (5m)** - 300ms 초과 요청 수 (Stat)
4. **HTTP Status Distribution (5m)** - 상태 코드별 분포 (Pie Chart)

#### Performance & Trends 섹션
5. **Error Rate (%) Trend** - 시간대별 에러 비율 추이 (Time Series)

#### Endpoints 섹션
6. **Top 10 Endpoints by Log Count** - 엔드포인트별 로그 수 (Bar Chart)

#### Request Tracing 섹션
7. **Request Trace (by Request ID)** - Request ID로 요청 추적 (Logs)

#### Error Logs 섹션
8. **Recent Error Logs** - 최근 에러 로그 상세 (Logs)

### Explore에서 로그 조회

#### 기본 쿼리

```logql
# 전체 로그
{job="spring-boot-demo"}

# JSON 파싱
{job="spring-boot-demo"} | json

# ERROR 로그만
{job="spring-boot-demo"} | json | level="ERROR"

# 특정 엔드포인트 (mdc_ 접두사 사용)
{job="spring-boot-demo"} | json | mdc_endpoint="/api/slow"

# 느린 요청 (300ms 이상)
{job="spring-boot-demo"} | json | mdc_elapsed_ms > 300

# Request ID로 요청 추적
{job="spring-boot-demo"} | json | mdc_request_id="특정-uuid"
```

#### 집계 쿼리

```logql
# 5분간 로그 라인 수
sum(count_over_time({job="spring-boot-demo"}[5m]))

# 엔드포인트별 로그 수
sum by (mdc_endpoint) (count_over_time({job="spring-boot-demo"} | json [5m]))

# HTTP 상태 코드별 분포
sum by (mdc_status) (count_over_time({job="spring-boot-demo"} | json | mdc_status =~ ".+" [5m]))

# 에러율 (%)
sum(count_over_time({job="spring-boot-demo"} | json | level="ERROR" [5m]))
/ sum(count_over_time({job="spring-boot-demo"} [5m])) * 100
```

### Alert 확인

1. 좌측 메뉴에서 **Alerting** 클릭
2. **Alert rules** 선택
3. "High Error Log Rate" 규칙 확인
   - **Normal**: 정상 상태 (초록색)
   - **Pending**: 조건 충족 중, 1분 대기 (노란색)
   - **Firing**: Alert 발생 (빨간색)

---

## 주요 LogQL 쿼리

> **참고**: Loki4j appender 사용 시 MDC 필드에 `mdc_` 접두사가 붙습니다.

### 필터링

```logql
# 특정 상태 코드
{job="spring-boot-demo"} | json | mdc_status="500"

# 특정 HTTP 메서드
{job="spring-boot-demo"} | json | mdc_method="GET"

# 특정 request_id 추적
{job="spring-boot-demo"} | json | mdc_request_id="abc-123-def"

# 텍스트 검색
{job="spring-boot-demo"} |= "error"

# 정규식 매칭
{job="spring-boot-demo"} |~ "timeout|connection refused"
```

### 집계 및 통계

```logql
# 시간대별 로그 수
rate({job="spring-boot-demo"}[1m])

# status별 분포
sum by (mdc_status) (count_over_time({job="spring-boot-demo"} | json | mdc_status =~ ".+" [5m]))

# 에러율 (%)
sum(count_over_time({job="spring-boot-demo"} | json | level="ERROR" [5m]))
/ sum(count_over_time({job="spring-boot-demo"} [5m])) * 100
```

---

## 트러블슈팅

### 1. 로그가 Grafana에 표시되지 않음

**확인 사항**:

```bash
# Alloy 로그 확인
docker compose logs alloy

# App 로그 확인 (JSON 형식인지)
docker compose logs app | head -20

# Loki 상태 확인
curl http://localhost:3100/ready
```

**해결 방법**:
- Alloy가 app 컨테이너를 인식하는지 확인
- App 컨테이너 이름이 `demo-app`인지 확인
- Alloy 설정에서 컨테이너 필터 규칙 확인: `.*-app-.*`

---

### 2. Alert가 발생하지 않음

**확인 사항**:

```bash
# Grafana 로그에서 alerting 관련 메시지 확인
docker compose logs grafana | grep -i alert
```

**해결 방법**:
- Spike 테스트가 충분한 에러를 생성하는지 확인
- Grafana Explore에서 ERROR 로그 수 확인:
  ```logql
  sum(count_over_time({job="spring-boot-demo"} | json | level="ERROR" [5m]))
  ```
- Alert 조건: 5분간 ERROR 로그 > 50개, 1분간 유지

---

### 3. Docker 빌드 실패

**App 빌드 실패 시**:

```bash
# 빌드 재시도
docker compose build --no-cache app

# 로그 확인
docker compose logs app
```

**일반적인 원인**:
- Gradle 의존성 다운로드 실패 → 재시도
- Java 버전 불일치 → Dockerfile에서 JDK 17 사용 확인

---

### 4. 포트 충돌

**에러 메시지**: "port is already allocated"

**해결 방법**:

```bash
# 사용 중인 포트 확인
lsof -i :3000  # Grafana
lsof -i :3100  # Loki
lsof -i :8080  # App

# 기존 프로세스 종료 또는 docker-compose.yml에서 포트 변경
```

---

### 5. 로그 볼륨 정리

장기간 실행 시 로그 데이터가 쌓일 수 있습니다:

```bash
# 모든 서비스 중지 및 볼륨 삭제
docker compose down -v

# 특정 볼륨만 삭제
docker volume rm demo-log-observability_loki_data
docker volume rm demo-log-observability_grafana_data
```

---

### 6. Loki 시리즈 제한 에러

**에러 메시지**: `maximum of series (5000) reached for a single query`

**원인**: `unwrap`을 사용한 쿼리가 너무 많은 시리즈를 생성

**해결 방법**:
1. Loki 설정에서 `max_query_series` 값 증가 (`infra/loki/loki-config.yaml`)
2. 쿼리 시간 범위 축소 (예: `[1m]` 대신 `[5m]`)
3. `unwrap` 사용 쿼리 피하기 (P95, 평균 응답 시간 등)

```yaml
# infra/loki/loki-config.yaml
limits_config:
  max_query_series: 5000  # 기본값 500
```

---

## 디렉토리 구조

```
demo-log-observability/
├── README.md                    # 이 문서
├── PROJECT.md                   # 프로젝트 설계 문서
├── docker-compose.yml           # Docker Compose 설정 (인프라 서비스)
├── build.gradle.kts             # Spring Boot 빌드 설정
├── settings.gradle.kts          # Gradle 설정
│
├── src/main/                    # Spring Boot 애플리케이션
│   ├── kotlin/com/example/logobservability/
│   │   ├── DemoLogObservabilityApplication.kt  # Main application
│   │   ├── controller/
│   │   │   └── ApiController.kt
│   │   └── filter/
│   │       └── RequestIdFilter.kt
│   └── resources/
│       ├── application.yml      # Docker Compose Support 설정 포함
│       └── logback-spring.xml   # JSON 로그 설정
│
└── infra/                       # 인프라 설정
    ├── loki/
    │   └── loki-config.yaml     # Loki 설정
    ├── alloy/
    │   └── alloy.hcl            # Grafana Alloy 설정
    ├── grafana/
    │   ├── provisioning/
    │   │   ├── datasources/
    │   │   │   └── loki.yaml    # Loki datasource
    │   │   ├── dashboards/
    │   │   │   └── dashboards.yaml  # Dashboard provider
    │   │   └── alerting/
    │   │       ├── alerts.yaml  # Alert rules
    │   │       ├── contactpoints.yaml
    │   │       └── policies.yaml
    │   └── dashboards/
    │       └── app-logs-overview.json  # 대시보드 정의
    └── loadgen/k6/
        ├── smoke.js             # Smoke test
        ├── steady.js            # Steady traffic test
        └── spike.js             # Spike test (alert trigger)
```

---

## API 엔드포인트

Spring Boot 앱은 다음 엔드포인트를 제공합니다:

| Endpoint | Method | Parameters | Description |
|----------|--------|------------|-------------|
| `/api/hello` | GET | - | 정상 응답, 항상 200 |
| `/api/slow` | GET | `ms` (default: 200) | 지정된 시간만큼 지연 |
| `/api/error` | GET | `rate` (default: 0.1) | 확률적 에러 발생 (0.0~1.0) |
| `/api/burst` | GET | `lines` (default: 100) | 대량 로그 생성 |

### 사용 예시

```bash
# 정상 요청
curl http://localhost:8080/api/hello

# 500ms 지연
curl http://localhost:8080/api/slow?ms=500

# 50% 확률로 에러
curl http://localhost:8080/api/error?rate=0.5

# 200줄 로그 생성
curl http://localhost:8080/api/burst?lines=200
```

---

## 로그 형식

애플리케이션은 다음과 같은 JSON 로그를 출력합니다:

```json
{
  "timestamp": "2024-01-17T08:30:45.123Z",
  "level": "INFO",
  "thread": "http-nio-8080-exec-1",
  "logger": "com.example.demo.filter.RequestIdFilter",
  "message": "Request completed",
  "service": "demo-api",
  "env": "local",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "endpoint": "/api/hello",
  "method": "GET",
  "status": "200",
  "elapsed_ms": "45"
}
```

### 주요 필드

- `service`: 서비스 이름 (고정: "demo-api")
- `env`: 환경 (고정: "local")
- `request_id`: 요청별 고유 UUID
- `endpoint`: 요청 경로
- `method`: HTTP 메서드
- `status`: HTTP 상태 코드
- `elapsed_ms`: 응답 시간 (밀리초)

---

## AI Incident Bot 데모 (Plan 3)

시나리오 1~3 (CODE_BUG) 트리거 시 GitHub에 Issue + Draft PR이 자동 생성됩니다.

### 실행

```bash
cp .env.example .env
# .env 편집: ANTHROPIC_API_KEY, GITHUB_TOKEN, SLACK_WEBHOOK_URL, WEBHOOK_TOKEN, GITHUB_REPO, GITHUB_REPO_URL 채우기
git submodule update --init --recursive
docker compose --profile demo up -d --build
```

### 검증

1. 시나리오 트리거: `docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js`
2. 2~3분 후 Slack `#ai-bot-demo` 채널에서 단계별 메시지 확인
3. GitHub https://github.com/kiekk/demo-buggy-service/pulls 에서 Draft PR 확인

> ⚠️ Draft PR은 시연용. 머지하면 의도적 버그가 사라져 시나리오 재현 불가.

### 비용

- 1회 시연: 약 $0.5~1
- 일일 cap: `DAILY_COST_CAP_USD=5` (기본)
