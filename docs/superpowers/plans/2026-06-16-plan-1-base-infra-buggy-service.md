# Plan 1: 베이스 인프라 + demo-buggy-service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시나리오 1~3(CODE_BUG: NPE / 0나눗셈 / enum 매핑) 트리거 시 Loki에 로그 적재 + Grafana Alert 발화 + Webhook 호출까지 동작하는 인프라를 완성한다. 이 plan이 끝나면 `docker compose --profile demo up -d` 한 줄로 모든 인프라가 기동되고, k6로 시나리오 1~3을 트리거하면 echo 서버에 Grafana Webhook 페이로드가 도착하는 것까지 검증된다.

**Architecture:** 별도 GitHub 레포 `demo-buggy-service`(Spring Boot 3.4 / Kotlin / Java 21 / JPA + Flyway + PostgreSQL)를 새로 만들고, 기존 `demo-log-observability/` 디렉토리에 **git submodule**로 마운트한다. docker-compose는 새 profile `demo`에 postgres + buggy-service를 추가하고, Alloy/Grafana 설정도 buggy-service 컨테이너를 인식하도록 확장한다. AI 봇은 아직 만들지 않으며 webhook 수신 검증용으로 임시 Python echo 서버를 띄운다.

**Tech Stack:**
- Spring Boot 3.4.x, Kotlin 1.9, Java 21
- Spring Data JPA, Flyway, HikariCP
- PostgreSQL 16-alpine
- `com.gorylenko.gradle-git-properties` 2.4.2
- `net.logstash.logback:logstash-logback-encoder` 7.4
- 기존 LGTM 스택: Alloy v1.0.0 / Loki 2.9.3 / Grafana 10.2.3
- k6 0.48.0 (기존)
- Python 3.12 표준 라이브러리 `http.server` (임시 webhook echo)

**관련 spec:** `docs/superpowers/specs/2026-06-16-ai-incident-bot-demo-design.md`

---

## 사전 작업 (사람이 수동으로 처리)

이 plan을 시작하기 전 사용자가 해야 하는 작업.

- [x] **A. GitHub에 레포 `demo-buggy-service` 생성** (완료)
  - 레포: https://github.com/kiekk/demo-buggy-service
  - clone URL (SSH): `git@github.com:kiekk/demo-buggy-service.git`
  - clone URL (HTTPS): `https://github.com/kiekk/demo-buggy-service.git`
  - public/private 무관 (private이면 GitHub PAT 또는 SSH 키 필요. Plan 3에서 PAT 별도 필요)

- [ ] **B. 로컬 워크스페이스 디렉토리 생성**
  - `~/Documents/study/demo-log-observability/demo-log-observability/`의 옆이 아니라 같은 부모 디렉토리에 클론할 위치를 결정 (예: 시연 workspace를 `~/dev/buggy-demo/`로 클론)
  - 이 plan에서는 demo-buggy-service를 demo-log-observability에 submodule로 마운트하므로, 별도로 clone할 필요는 없다. 단 GitHub 레포 URL은 필요.

- [ ] **C. 환경변수 준비**
  - `GITHUB_OWNER=kiekk`, `GITHUB_REPO_NAME=demo-buggy-service`, `GITHUB_REPO=kiekk/demo-buggy-service`
  - Personal Access Token (PAT, repo 권한)은 Plan 3에서 사용. Plan 1에서는 불필요.

---

## File Structure

이 Plan에서 생성/수정할 파일들. 데모 작업 디렉토리는 `~/Documents/study/demo-log-observability/demo-log-observability/` (이하 `$REPO`로 표기).

### 새 GitHub 레포 `demo-buggy-service` (Task 1~10에서 생성)

```
demo-buggy-service/                         (Task 1: clone + Spring Initializr)
├── README.md                               (Task 1)
├── .gitignore                              (Task 1, Initializr 기본)
├── build.gradle.kts                        (Task 2)
├── settings.gradle.kts                     (Task 1)
├── gradlew, gradlew.bat, gradle/wrapper/   (Task 1, Initializr)
├── Dockerfile                              (Task 10)
├── src/main/kotlin/com/example/buggy/
│   ├── BuggyServiceApplication.kt          (Task 1)
│   ├── config/
│   │   ├── CommitShaProvider.kt            (Task 6)
│   │   ├── RequestIdFilter.kt              (Task 6)
│   │   └── WebConfig.kt                    (Task 6)
│   ├── domain/
│   │   ├── User.kt                         (Task 3)
│   │   ├── Address.kt                      (Task 3)
│   │   ├── Order.kt                        (Task 3)
│   │   ├── OrderStatus.kt                  (Task 3)
│   │   └── Inventory.kt                    (Task 3)
│   ├── repository/
│   │   ├── UserRepository.kt               (Task 4)
│   │   ├── AddressRepository.kt            (Task 4)
│   │   ├── OrderRepository.kt              (Task 4)
│   │   └── InventoryRepository.kt          (Task 4)
│   ├── controller/
│   │   ├── UserController.kt               (Task 7 — 시나리오 1 NPE)
│   │   ├── CartController.kt               (Task 8 — 시나리오 2 div by 0)
│   │   └── OrderController.kt              (Task 9 — 시나리오 3 enum)
│   └── dto/
│       ├── ProfileResponse.kt              (Task 7)
│       ├── DiscountResponse.kt             (Task 8)
│       └── OrderCreateRequest.kt           (Task 9)
├── src/main/resources/
│   ├── application.yml                     (Task 2)
│   ├── logback-spring.xml                  (Task 2)
│   └── db/migration/
│       ├── V1__init_schema.sql             (Task 5)
│       └── V2__seed_data.sql               (Task 5)
└── src/test/kotlin/com/example/buggy/
    ├── controller/
    │   ├── UserControllerTest.kt           (Task 7)
    │   ├── CartControllerTest.kt           (Task 8)
    │   └── OrderControllerTest.kt          (Task 9)
    └── support/
        └── PostgresTestContainer.kt        (Task 5)
```

### 기존 demo-log-observability 디렉토리 수정 (Task 11~16)

```
$REPO/
├── .gitmodules                             (Task 11 신규)
├── demo-buggy-service/                     (Task 11 submodule 마운트)
├── docker-compose.yml                      (Task 11 수정)
├── .env.example                            (Task 15 신규)
├── infra/
│   ├── postgres/
│   │   └── init.sql                        (Task 11 신규)
│   ├── alloy/alloy.hcl                     (Task 12 수정)
│   ├── grafana/provisioning/alerting/
│   │   ├── alerts.yaml                     (Task 13 수정)
│   │   └── contactpoints.yaml              (Task 13 수정)
│   └── loadgen/k6/
│       ├── scenario-1-npe.js               (Task 14 신규)
│       ├── scenario-2-divzero.js           (Task 14 신규)
│       └── scenario-3-enum.js              (Task 14 신규)
└── tools/
    └── webhook-echo/
        └── server.py                       (Task 15 신규 임시 webhook 검증용)
```

---

## Task 1: demo-buggy-service 레포 초기화 (Spring Boot Initializr)

**Files:**
- Create: `demo-buggy-service/` (전체 디렉토리, Spring Initializr가 생성)
- Create: `demo-buggy-service/src/main/kotlin/com/example/buggy/BuggyServiceApplication.kt`

이 task는 사용자 환경에서 새 디렉토리 생성으로 시작한다. 이후 task들의 모든 경로는 이 레포 내부 경로다.

- [ ] **Step 1: Spring Initializr로 프로젝트 zip 다운로드**

Run:
```bash
mkdir -p ~/dev && cd ~/dev
curl -G https://start.spring.io/starter.zip \
  --data-urlencode "type=gradle-project-kotlin" \
  --data-urlencode "language=kotlin" \
  --data-urlencode "bootVersion=3.4.0" \
  --data-urlencode "baseDir=demo-buggy-service" \
  --data-urlencode "groupId=com.example" \
  --data-urlencode "artifactId=buggy-service" \
  --data-urlencode "name=buggy-service" \
  --data-urlencode "description=Demo Buggy Service for AI Incident Bot" \
  --data-urlencode "packageName=com.example.buggy" \
  --data-urlencode "packaging=jar" \
  --data-urlencode "javaVersion=21" \
  --data-urlencode "dependencies=web,data-jpa,validation,actuator,flyway,postgresql" \
  -o buggy-service.zip
unzip buggy-service.zip
rm buggy-service.zip
ls demo-buggy-service/
```

Expected: `HELP.md  build.gradle.kts  gradle  gradlew  gradlew.bat  settings.gradle.kts  src` 출력.

- [ ] **Step 2: 기본 메인 클래스 확인**

Run:
```bash
cat ~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/BuggyServiceApplication.kt
```

Expected output:
```kotlin
package com.example.buggy

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class BuggyServiceApplication

fun main(args: Array<String>) {
    runApplication<BuggyServiceApplication>(*args)
}
```

- [ ] **Step 3: GitHub 레포에 push**

Run (SSH 키 셋업되어 있다면 SSH, 아니면 HTTPS):
```bash
cd ~/dev/demo-buggy-service
git init
git add .
git commit -m "chore: initial Spring Boot scaffold from start.spring.io"
git branch -M main
# SSH
git remote add origin git@github.com:kiekk/demo-buggy-service.git
# 또는 HTTPS
# git remote add origin https://github.com/kiekk/demo-buggy-service.git
git push -u origin main
```

Expected: GitHub에서 레포에 코드가 올라간 것 확인.

- [ ] **Step 4: README.md 작성**

Create `~/dev/demo-buggy-service/README.md`:

```markdown
# demo-buggy-service

AI Incident Bot 데모용 의도적으로 깨진 코드를 담은 Spring Boot 서비스.

각 시나리오는 git tag로 분리되어 있다.

| Tag | 시나리오 | 카테고리 |
|---|---|---|
| `scenario-1` | UserController.getProfile NPE | CODE_BUG |
| `scenario-2` | CartController.discount 0 나눗셈 | CODE_BUG |
| `scenario-3` | OrderController.create enum 매핑 실패 | CODE_BUG |
| `scenario-4` | (추후) addresses.city 빈 문자열 | DATA_ANOMALY |
| `scenario-5` | (추후) /api/reports/heavy HikariCP 풀 고갈 | INFRA_ISSUE |
| `scenario-6` | (추후) /api/download/large ClientAbortException | BENIGN_ERROR |

상위 데모 프로젝트: [demo-log-observability](https://github.com/kiekk/demo-log-observability)
```

- [ ] **Step 5: Commit & push**

Run:
```bash
cd ~/dev/demo-buggy-service
git add README.md
git commit -m "docs: add README with scenario table"
git push
```

Expected: GitHub에 README가 올라간 것 확인.

---

## Task 2: build.gradle.kts에 의존성 추가 + logback + application.yml

**Files:**
- Modify: `~/dev/demo-buggy-service/build.gradle.kts`
- Create: `~/dev/demo-buggy-service/src/main/resources/logback-spring.xml`
- Modify: `~/dev/demo-buggy-service/src/main/resources/application.yml` (기존 properties → yml 교체)

- [ ] **Step 1: build.gradle.kts 작성**

`~/dev/demo-buggy-service/build.gradle.kts`를 다음으로 교체:

```kotlin
plugins {
    kotlin("jvm") version "1.9.25"
    kotlin("plugin.spring") version "1.9.25"
    kotlin("plugin.jpa") version "1.9.25"
    id("org.springframework.boot") version "3.4.0"
    id("io.spring.dependency-management") version "1.1.6"
    id("com.gorylenko.gradle-git-properties") version "2.4.2"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.flywaydb:flyway-core")
    implementation("org.flywaydb:flyway-database-postgresql")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.jetbrains.kotlin:kotlin-reflect")
    implementation("net.logstash.logback:logstash-logback-encoder:7.4")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter:1.20.3")
    testImplementation("org.testcontainers:postgresql:1.20.3")
    testImplementation("com.h2database:h2")
}

kotlin {
    compilerOptions {
        freeCompilerArgs.addAll("-Xjsr305=strict")
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
}

gitProperties {
    keys = listOf("git.commit.id.abbrev", "git.commit.id.full", "git.commit.time", "git.branch")
    failOnNoGitDirectory = false
}
```

- [ ] **Step 2: Gradle build 검증**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew build -x test
```

Expected: `BUILD SUCCESSFUL`, `build/resources/main/git.properties` 생성됨

- [ ] **Step 3: application.properties → application.yml로 교체**

기존 `~/dev/demo-buggy-service/src/main/resources/application.properties`를 삭제하고 `application.yml`로 생성:

```bash
rm ~/dev/demo-buggy-service/src/main/resources/application.properties
```

Create `~/dev/demo-buggy-service/src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: demo-buggy-service
  datasource:
    url: ${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/buggy}
    username: ${SPRING_DATASOURCE_USERNAME:buggy}
    password: ${SPRING_DATASOURCE_PASSWORD:buggy}
    hikari:
      maximum-pool-size: ${SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE:10}
      minimum-idle: 2
      connection-timeout: 5000
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: false
  flyway:
    enabled: true
    locations: classpath:db/migration

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    git:
      mode: full
```

- [ ] **Step 4: logback-spring.xml 작성 (JSON 로그 + commit_sha MDC)**

Create `~/dev/demo-buggy-service/src/main/resources/logback-spring.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <customFields>{"service":"demo-buggy-service","env":"local"}</customFields>
            <includeMdcKeyName>request_id</includeMdcKeyName>
            <includeMdcKeyName>endpoint</includeMdcKeyName>
            <includeMdcKeyName>method</includeMdcKeyName>
            <includeMdcKeyName>status</includeMdcKeyName>
            <includeMdcKeyName>elapsed_ms</includeMdcKeyName>
            <includeMdcKeyName>commit_sha</includeMdcKeyName>
            <includeMdcKeyName>exception_class</includeMdcKeyName>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

- [ ] **Step 5: 빌드 + 컨테이너 없이 컴파일 가능한지 확인**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew compileKotlin
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 6: Commit & push**

Run:
```bash
cd ~/dev/demo-buggy-service
git add build.gradle.kts src/main/resources/
git commit -m "chore: add JPA/Flyway/logstash deps and JSON log config"
git push
```

---

## Task 3: 도메인 모델 (User, Address, Order, OrderStatus, Inventory)

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/User.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/Address.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/Order.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/OrderStatus.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/Inventory.kt`

데이터 클래스 + JPA 엔티티. JPA Entity는 `@Entity` + 빈 생성자가 필요하므로 `open class`로 둔다 (Kotlin spring plugin이 자동 처리하지만 명시적으로 작성).

- [ ] **Step 1: OrderStatus enum 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/OrderStatus.kt`:

```kotlin
package com.example.buggy.domain

enum class OrderStatus {
    CREATED,
    PAID,
    SHIPPED,
    CANCELED,
}
```

- [ ] **Step 2: User Entity 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/User.kt`:

```kotlin
package com.example.buggy.domain

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "users")
class User(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(nullable = false)
    val name: String,

    @Column(nullable = false)
    val email: String,
)
```

- [ ] **Step 3: Address Entity 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/Address.kt`:

```kotlin
package com.example.buggy.domain

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "addresses")
class Address(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(name = "user_id", nullable = false)
    val userId: Long,

    @Column
    val street: String?,

    @Column
    val city: String?,
)
```

> 시나리오 4 (DATA_ANOMALY)에서 `city`가 빈 문자열로 들어가는 케이스를 다루므로 `nullable=true`로 둠.

- [ ] **Step 4: Order Entity 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/Order.kt`:

```kotlin
package com.example.buggy.domain

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.EnumType
import jakarta.persistence.Enumerated
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "orders")
class Order(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,

    @Column(name = "user_id", nullable = false)
    val userId: Long,

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    val status: OrderStatus,

    @Column(name = "total_amount", nullable = false)
    val totalAmount: Int,
)
```

- [ ] **Step 5: Inventory Entity 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/domain/Inventory.kt`:

```kotlin
package com.example.buggy.domain

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.Id
import jakarta.persistence.Table

@Entity
@Table(name = "inventory")
class Inventory(
    @Id
    @Column(name = "sku")
    val sku: String,

    @Column(nullable = false)
    val stock: Int,
)
```

- [ ] **Step 6: 컴파일 확인**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew compileKotlin
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 7: Commit & push**

Run:
```bash
git add src/main/kotlin/com/example/buggy/domain/
git commit -m "feat(domain): add User, Address, Order, OrderStatus, Inventory entities"
git push
```

---

## Task 4: JPA Repositories

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/UserRepository.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/AddressRepository.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/OrderRepository.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/InventoryRepository.kt`

- [ ] **Step 1: UserRepository**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/UserRepository.kt`:

```kotlin
package com.example.buggy.repository

import com.example.buggy.domain.User
import org.springframework.data.jpa.repository.JpaRepository

interface UserRepository : JpaRepository<User, Long>
```

- [ ] **Step 2: AddressRepository**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/AddressRepository.kt`:

```kotlin
package com.example.buggy.repository

import com.example.buggy.domain.Address
import org.springframework.data.jpa.repository.JpaRepository

interface AddressRepository : JpaRepository<Address, Long> {
    fun findByUserId(userId: Long): Address?
}
```

- [ ] **Step 3: OrderRepository**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/OrderRepository.kt`:

```kotlin
package com.example.buggy.repository

import com.example.buggy.domain.Order
import org.springframework.data.jpa.repository.JpaRepository

interface OrderRepository : JpaRepository<Order, Long>
```

- [ ] **Step 4: InventoryRepository**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/repository/InventoryRepository.kt`:

```kotlin
package com.example.buggy.repository

import com.example.buggy.domain.Inventory
import org.springframework.data.jpa.repository.JpaRepository

interface InventoryRepository : JpaRepository<Inventory, String>
```

- [ ] **Step 5: 컴파일 확인**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew compileKotlin
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 6: Commit & push**

```bash
git add src/main/kotlin/com/example/buggy/repository/
git commit -m "feat(repository): add JPA repositories for User/Address/Order/Inventory"
git push
```

---

## Task 5: Flyway 마이그레이션 V1 (스키마) + V2 (seed data)

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/resources/db/migration/V1__init_schema.sql`
- Create: `~/dev/demo-buggy-service/src/main/resources/db/migration/V2__seed_data.sql`
- Create: `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/support/PostgresTestContainer.kt`
- Create: `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/MigrationTest.kt`

먼저 마이그레이션이 Testcontainers postgres에서 실제로 적용되는지 확인하는 테스트부터 작성한다 (TDD).

- [ ] **Step 1: TestContainer helper 작성**

Create `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/support/PostgresTestContainer.kt`:

```kotlin
package com.example.buggy.support

import org.testcontainers.containers.PostgreSQLContainer

object PostgresTestContainer {
    val instance: PostgreSQLContainer<*> = PostgreSQLContainer("postgres:16-alpine")
        .withDatabaseName("buggy")
        .withUsername("buggy")
        .withPassword("buggy")
        .also { it.start() }
}
```

- [ ] **Step 2: 실패하는 MigrationTest 작성**

Create `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/MigrationTest.kt`:

```kotlin
package com.example.buggy

import com.example.buggy.repository.AddressRepository
import com.example.buggy.repository.InventoryRepository
import com.example.buggy.repository.OrderRepository
import com.example.buggy.repository.UserRepository
import com.example.buggy.support.PostgresTestContainer
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource

@SpringBootTest
class MigrationTest {

    @Autowired private lateinit var users: UserRepository
    @Autowired private lateinit var addresses: AddressRepository
    @Autowired private lateinit var orders: OrderRepository
    @Autowired private lateinit var inventory: InventoryRepository

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
    fun `V1 schema and V2 seed should be applied`() {
        // V2 seed가 들어있다고 가정
        assertThat(users.count()).isGreaterThanOrEqualTo(200L)
        assertThat(addresses.count()).isGreaterThanOrEqualTo(200L)
        assertThat(inventory.count()).isGreaterThanOrEqualTo(1L)

        // 시나리오 4 검증: user_id 100~200 구간 중 일부에 city='' 또는 NULL
        val brokenAddresses = addresses.findAll().filter {
            (it.userId in 100..200) && (it.city.isNullOrBlank())
        }
        assertThat(brokenAddresses).isNotEmpty
    }
}
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.MigrationTest"
```

Expected: FAIL — 마이그레이션 파일이 없어서 Flyway 또는 schema validation 에러

- [ ] **Step 4: V1 스키마 마이그레이션 작성**

Create `~/dev/demo-buggy-service/src/main/resources/db/migration/V1__init_schema.sql`:

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL
);

CREATE TABLE addresses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    street VARCHAR(255),
    city VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_addresses_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX idx_addresses_user_id ON addresses(user_id);

CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount INTEGER NOT NULL,
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE inventory (
    sku VARCHAR(64) PRIMARY KEY,
    stock INTEGER NOT NULL
);
```

> Address 엔티티에 `created_at`, `updated_at` 필드가 없는데도 컬럼을 만드는 이유: 시나리오 4 DATA_ANOMALY Issue 본문의 검증 SQL에서 `created_at`을 쓰기 때문. JPA에서는 사용 안 함.

- [ ] **Step 5: V2 seed data 작성 (시나리오 4용 broken row 포함)**

Create `~/dev/demo-buggy-service/src/main/resources/db/migration/V2__seed_data.sql`:

```sql
-- 250명의 사용자 생성
INSERT INTO users (id, name, email)
SELECT i, 'User ' || i, 'user' || i || '@example.com'
FROM generate_series(1, 250) AS i;

ALTER SEQUENCE users_id_seq RESTART WITH 251;

-- 모든 사용자에게 주소 — user_id 100~200 구간 중 일부는 city=''로 의도적 손상
INSERT INTO addresses (user_id, street, city)
SELECT
    i,
    '123 Street ' || i,
    CASE
        WHEN i BETWEEN 100 AND 200 AND i % 3 = 0 THEN ''   -- 시나리오 4 broken
        WHEN i BETWEEN 100 AND 200 AND i % 7 = 0 THEN NULL -- 시나리오 4 broken
        ELSE 'City ' || i
    END
FROM generate_series(1, 250) AS i;

-- Inventory seed (시나리오 6 race condition은 차후 plan에서 사용)
INSERT INTO inventory (sku, stock) VALUES
    ('SKU-A', 100),
    ('SKU-B', 50);
```

- [ ] **Step 6: 테스트 재실행 (통과 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.MigrationTest"
```

Expected: `BUILD SUCCESSFUL`, 1 test passed

- [ ] **Step 7: Commit & push**

```bash
git add src/main/resources/db/migration/ src/test/kotlin/
git commit -m "feat(db): add V1 schema and V2 seed (with intentional data anomaly)"
git push
```

---

## Task 6: RequestIdFilter + CommitShaProvider (MDC commit_sha)

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/config/CommitShaProvider.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/config/RequestIdFilter.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/config/WebConfig.kt`
- Create: `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/config/RequestIdFilterTest.kt`

- [ ] **Step 1: RequestIdFilter 테스트 작성 (실패 케이스)**

Create `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/config/RequestIdFilterTest.kt`:

```kotlin
package com.example.buggy.config

import com.example.buggy.support.PostgresTestContainer
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.get
import org.springframework.test.web.servlet.result.MockMvcResultHandlers.print

@SpringBootTest
@AutoConfigureMockMvc
class RequestIdFilterTest {
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
    fun `request to actuator health should populate request_id header`() {
        val response = mvc.get("/actuator/health").andDo { print() }.andReturn().response
        val requestId = response.getHeader("X-Request-Id")
        assertThat(requestId).isNotNull().isNotBlank()
    }
}
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.config.RequestIdFilterTest"
```

Expected: FAIL — `X-Request-Id` 헤더가 null

- [ ] **Step 3: CommitShaProvider 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/config/CommitShaProvider.kt`:

```kotlin
package com.example.buggy.config

import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component

@Component
class CommitShaProvider(
    @Value("\${git.commit.id.abbrev:unknown}") val sha: String,
)
```

- [ ] **Step 4: RequestIdFilter 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/config/RequestIdFilter.kt`:

```kotlin
package com.example.buggy.config

import jakarta.servlet.FilterChain
import jakarta.servlet.http.HttpServletRequest
import jakarta.servlet.http.HttpServletResponse
import org.slf4j.LoggerFactory
import org.slf4j.MDC
import org.springframework.core.Ordered
import org.springframework.core.annotation.Order
import org.springframework.stereotype.Component
import org.springframework.web.filter.OncePerRequestFilter
import java.util.UUID

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestIdFilter(
    private val commitShaProvider: CommitShaProvider,
) : OncePerRequestFilter() {

    private val logger = LoggerFactory.getLogger(javaClass)

    override fun doFilterInternal(
        request: HttpServletRequest,
        response: HttpServletResponse,
        chain: FilterChain,
    ) {
        val requestId = UUID.randomUUID().toString()
        val start = System.currentTimeMillis()
        MDC.put("request_id", requestId)
        MDC.put("endpoint", request.requestURI)
        MDC.put("method", request.method)
        MDC.put("commit_sha", commitShaProvider.sha)
        response.setHeader("X-Request-Id", requestId)

        try {
            chain.doFilter(request, response)
        } catch (e: Exception) {
            MDC.put("exception_class", e.javaClass.simpleName)
            throw e
        } finally {
            val elapsed = System.currentTimeMillis() - start
            MDC.put("status", response.status.toString())
            MDC.put("elapsed_ms", elapsed.toString())
            logger.info("Request completed")
            MDC.clear()
        }
    }
}
```

- [ ] **Step 5: WebConfig (필요 시) 빈 등록**

`@Component` 어노테이션이 있으므로 별도 WebConfig는 불필요. 빈 파일이 필요한 경우만 만들고, 기본은 생략. (이 step은 검증만)

Run:
```bash
ls ~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/config/
```

Expected: `CommitShaProvider.kt  RequestIdFilter.kt`

- [ ] **Step 6: 테스트 재실행**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.config.RequestIdFilterTest"
```

Expected: PASS

- [ ] **Step 7: Commit & push**

```bash
git add src/main/kotlin/com/example/buggy/config/ src/test/kotlin/com/example/buggy/config/
git commit -m "feat(filter): add RequestIdFilter populating MDC with request_id/commit_sha"
git push
```

---

## Task 7: 시나리오 1 — UserController NPE (CODE_BUG)

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/controller/UserController.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/ProfileResponse.kt`
- Create: `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/controller/UserControllerTest.kt`

**의도적 버그**: `userRepository.findById(id).get()`로 호출. 존재하지 않는 id 호출 시 `NoSuchElementException`. 추가로 `address.street.uppercase()` 호출 시 address가 null이면 NPE.

- [ ] **Step 1: ProfileResponse DTO**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/ProfileResponse.kt`:

```kotlin
package com.example.buggy.dto

data class ProfileResponse(
    val userId: Long,
    val name: String,
    val street: String,
)
```

- [ ] **Step 2: 통합 테스트 작성 — 정상 + 실패 케이스**

Create `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/controller/UserControllerTest.kt`:

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
class UserControllerTest {
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
    fun `existing user with address returns 200`() {
        mvc.get("/api/users/1/profile").andExpect { status { isOk() } }
    }

    @Test
    fun `non-existing user causes 500 (intentional bug - no null check)`() {
        mvc.get("/api/users/999/profile").andExpect { status { is5xxServerError() } }
    }
}
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.UserControllerTest"
```

Expected: FAIL — 404 (컨트롤러 없음)

- [ ] **Step 4: UserController 작성 (의도적 버그 포함)**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/controller/UserController.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.dto.ProfileResponse
import com.example.buggy.repository.AddressRepository
import com.example.buggy.repository.UserRepository
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/users")
class UserController(
    private val users: UserRepository,
    private val addresses: AddressRepository,
) {
    @GetMapping("/{id}/profile")
    fun getProfile(@PathVariable id: Long): ProfileResponse {
        // 의도적 버그: id가 존재하지 않으면 NoSuchElementException 발생
        val user = users.findById(id).get()
        val address = addresses.findByUserId(id)
        // 의도적 버그: address가 null이면 NPE 발생
        return ProfileResponse(
            userId = user.id!!,
            name = user.name,
            street = address!!.street!!.uppercase(),
        )
    }
}
```

- [ ] **Step 5: 테스트 재실행**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.UserControllerTest"
```

Expected: PASS (2 tests). 두 번째 테스트는 의도적으로 5xx 응답 확인.

- [ ] **Step 6: Commit & push + tag**

```bash
cd ~/dev/demo-buggy-service
git add src/main/kotlin/com/example/buggy/controller/UserController.kt \
        src/main/kotlin/com/example/buggy/dto/ProfileResponse.kt \
        src/test/kotlin/com/example/buggy/controller/UserControllerTest.kt
git commit -m "feat(scenario-1): UserController.getProfile with intentional NPE on missing user/address"
git tag scenario-1
git push --tags
git push
```

Expected: GitHub에 tag `scenario-1`이 push됨

---

## Task 8: 시나리오 2 — CartController 0 나눗셈 (CODE_BUG)

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/controller/CartController.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/DiscountResponse.kt`
- Create: `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/controller/CartControllerTest.kt`

**의도적 버그**: `total / items` 계산 시 `items=0` 가드 없음 → `ArithmeticException`.

- [ ] **Step 1: DiscountResponse DTO**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/DiscountResponse.kt`:

```kotlin
package com.example.buggy.dto

data class DiscountResponse(
    val items: Int,
    val total: Int,
    val perItem: Int,
)
```

- [ ] **Step 2: 통합 테스트 작성**

Create `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/controller/CartControllerTest.kt`:

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
class CartControllerTest {
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
    fun `discount with items=2 returns 200`() {
        mvc.get("/api/cart/discount?items=2&total=100").andExpect { status { isOk() } }
    }

    @Test
    fun `discount with items=0 returns 500 (intentional bug - no zero guard)`() {
        mvc.get("/api/cart/discount?items=0&total=100").andExpect { status { is5xxServerError() } }
    }
}
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.CartControllerTest"
```

Expected: FAIL — 404

- [ ] **Step 4: CartController 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/controller/CartController.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.dto.DiscountResponse
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/cart")
class CartController {

    @GetMapping("/discount")
    fun discount(
        @RequestParam items: Int,
        @RequestParam total: Int,
    ): DiscountResponse {
        // 의도적 버그: items=0 가드 없음 → ArithmeticException
        val perItem = total / items
        return DiscountResponse(items = items, total = total, perItem = perItem)
    }
}
```

- [ ] **Step 5: 테스트 재실행**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.CartControllerTest"
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit & push + tag**

```bash
git add src/main/kotlin/com/example/buggy/controller/CartController.kt \
        src/main/kotlin/com/example/buggy/dto/DiscountResponse.kt \
        src/test/kotlin/com/example/buggy/controller/CartControllerTest.kt
git commit -m "feat(scenario-2): CartController.discount with intentional ArithmeticException"
git tag scenario-2
git push --tags
git push
```

---

## Task 9: 시나리오 3 — OrderController enum 매핑 실패 (CODE_BUG)

**Files:**
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/controller/OrderController.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/OrderCreateRequest.kt`
- Create: `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/OrderCreateResponse.kt`
- Create: `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/controller/OrderControllerTest.kt`

**의도적 버그**: `OrderStatus.valueOf(request.status)`로 직접 변환. enum에 없는 값(`LEGACY_TYPE`)이 들어오면 `IllegalArgumentException`.

- [ ] **Step 1: DTOs**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/OrderCreateRequest.kt`:

```kotlin
package com.example.buggy.dto

data class OrderCreateRequest(
    val userId: Long,
    val status: String,
    val totalAmount: Int,
)
```

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/dto/OrderCreateResponse.kt`:

```kotlin
package com.example.buggy.dto

data class OrderCreateResponse(
    val orderId: Long,
    val userId: Long,
    val status: String,
)
```

- [ ] **Step 2: 통합 테스트 작성**

Create `~/dev/demo-buggy-service/src/test/kotlin/com/example/buggy/controller/OrderControllerTest.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.support.PostgresTestContainer
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.http.MediaType
import org.springframework.test.context.DynamicPropertyRegistry
import org.springframework.test.context.DynamicPropertySource
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
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
    fun `valid status CREATED returns 200`() {
        val body = """{"userId":1,"status":"CREATED","totalAmount":1000}"""
        mvc.post("/api/orders") {
            contentType = MediaType.APPLICATION_JSON
            content = body
        }.andExpect { status { isOk() } }
    }

    @Test
    fun `legacy status LEGACY_TYPE returns 500 (intentional bug - no enum validation)`() {
        val body = """{"userId":1,"status":"LEGACY_TYPE","totalAmount":1000}"""
        mvc.post("/api/orders") {
            contentType = MediaType.APPLICATION_JSON
            content = body
        }.andExpect { status { is5xxServerError() } }
    }
}
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.OrderControllerTest"
```

Expected: FAIL — 404

- [ ] **Step 4: OrderController 작성**

Create `~/dev/demo-buggy-service/src/main/kotlin/com/example/buggy/controller/OrderController.kt`:

```kotlin
package com.example.buggy.controller

import com.example.buggy.domain.Order
import com.example.buggy.domain.OrderStatus
import com.example.buggy.dto.OrderCreateRequest
import com.example.buggy.dto.OrderCreateResponse
import com.example.buggy.repository.OrderRepository
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/api/orders")
class OrderController(
    private val orders: OrderRepository,
) {
    @PostMapping
    fun create(@RequestBody request: OrderCreateRequest): OrderCreateResponse {
        // 의도적 버그: valueOf 직접 호출 — 잘못된 값이면 IllegalArgumentException
        val status = OrderStatus.valueOf(request.status)
        val saved = orders.save(
            Order(
                userId = request.userId,
                status = status,
                totalAmount = request.totalAmount,
            )
        )
        return OrderCreateResponse(
            orderId = saved.id!!,
            userId = saved.userId,
            status = saved.status.name,
        )
    }
}
```

- [ ] **Step 5: 테스트 재실행**

Run:
```bash
cd ~/dev/demo-buggy-service
./gradlew test --tests "com.example.buggy.controller.OrderControllerTest"
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit & push + tag**

```bash
git add src/main/kotlin/com/example/buggy/controller/OrderController.kt \
        src/main/kotlin/com/example/buggy/dto/OrderCreateRequest.kt \
        src/main/kotlin/com/example/buggy/dto/OrderCreateResponse.kt \
        src/test/kotlin/com/example/buggy/controller/OrderControllerTest.kt
git commit -m "feat(scenario-3): OrderController.create with intentional enum valueOf failure"
git tag scenario-3
git push --tags
git push
```

---

## Task 10: Dockerfile + 전체 빌드 검증

**Files:**
- Create: `~/dev/demo-buggy-service/Dockerfile`
- Create: `~/dev/demo-buggy-service/.dockerignore`

- [ ] **Step 1: Dockerfile 작성 (multi-stage)**

Create `~/dev/demo-buggy-service/Dockerfile`:

```dockerfile
# Build stage
FROM gradle:8.10.2-jdk21-alpine AS builder
WORKDIR /app

# 전체 소스 복사 + git 디렉토리도 (gradle-git-properties가 필요)
COPY . .

# 테스트 제외하고 빌드 (CI에서 테스트는 별도 단계)
RUN gradle bootJar -x test --no-daemon

# Runtime stage
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app

COPY --from=builder /app/build/libs/*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

- [ ] **Step 2: .dockerignore 작성**

Create `~/dev/demo-buggy-service/.dockerignore`:

```
.gradle/
build/
.idea/
*.iml
out/
.DS_Store
README.md
HELP.md
```

> 주의: `.git/`은 ignore하면 안 됨 (gradle-git-properties가 빌드 시 git 정보 추출에 필요).

- [ ] **Step 3: Docker 이미지 빌드 검증**

Run:
```bash
cd ~/dev/demo-buggy-service
docker build -t demo-buggy-service:scenario-3 .
```

Expected: 이미지 빌드 성공. 마지막에 `Successfully tagged demo-buggy-service:scenario-3`.

- [ ] **Step 4: 컨테이너 단독 실행 검증 (DB 없이 시작 실패 확인)**

Run:
```bash
docker run --rm -p 8081:8080 demo-buggy-service:scenario-3 &
sleep 15
curl -s http://localhost:8081/actuator/health | head -c 200
docker stop $(docker ps -q --filter ancestor=demo-buggy-service:scenario-3) 2>/dev/null
```

Expected: Postgres 연결 실패로 컨테이너가 죽거나 health = DOWN 상태. DB가 없는 환경이라 정상.

- [ ] **Step 5: Commit & push**

```bash
git add Dockerfile .dockerignore
git commit -m "chore: add multi-stage Dockerfile and .dockerignore"
git push
```

---

## Task 11: demo-log-observability에 git submodule + docker-compose 확장 + postgres

이제 작업 디렉토리가 demo-buggy-service에서 **demo-log-observability**로 바뀐다.

**Files:**
- Modify: `~/Documents/study/demo-log-observability/demo-log-observability/.gitignore` (서브모듈 제외 안 함)
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/.gitmodules` (자동 생성)
- Modify: `~/Documents/study/demo-log-observability/demo-log-observability/docker-compose.yml`
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/infra/postgres/init.sql`

- [ ] **Step 1: git submodule 추가**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
# SSH (권장)
git submodule add git@github.com:kiekk/demo-buggy-service.git demo-buggy-service
# 또는 HTTPS
# git submodule add https://github.com/kiekk/demo-buggy-service.git demo-buggy-service
cat .gitmodules
```

Expected output:
```
[submodule "demo-buggy-service"]
        path = demo-buggy-service
        url = git@github.com:kiekk/demo-buggy-service.git
```

- [ ] **Step 2: postgres init 디렉토리 + init.sql**

Run:
```bash
mkdir -p ~/Documents/study/demo-log-observability/demo-log-observability/infra/postgres
```

Create `infra/postgres/init.sql`:

```sql
-- demo-buggy-service의 Flyway 마이그레이션이 스키마를 만든다.
-- 이 파일은 의도적으로 비워둔다 (DB 생성 자체는 docker-compose env로 처리).
SELECT 1;
```

- [ ] **Step 3: docker-compose.yml에 postgres + buggy-service + profile 추가**

기존 `docker-compose.yml`을 수정한다. 기존 services(loki, grafana, alloy, loadgen)는 그대로 유지하고 다음 services를 추가하고, 기존 `loadgen`의 profile을 `loadtest`에서 그대로 두되 새 profile `demo`를 추가한다.

`docker-compose.yml` 전체를 다음으로 교체:

```yaml
services:
  loki:
    image: grafana/loki:2.9.3
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./infra/loki/loki-config.yaml:/etc/loki/loki-config.yaml
      - loki_data:/loki
    command: -config.file=/etc/loki/loki-config.yaml
    networks:
      - observability-net
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.2.3
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_LOG_LEVEL=info
      - GF_UNIFIED_ALERTING_ENABLED=true
      - GF_ALERTING_ENABLED=false
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning
      - ./infra/grafana/dashboards:/etc/grafana/dashboards
      - grafana_data:/var/lib/grafana
    networks:
      - observability-net
    depends_on:
      - loki
    restart: unless-stopped

  alloy:
    image: grafana/alloy:v1.0.0
    container_name: alloy
    volumes:
      - ./infra/alloy/alloy.hcl:/etc/alloy/config.alloy
      - /var/run/docker.sock:/var/run/docker.sock
    command: run --server.http.listen-addr=0.0.0.0:12345 --storage.path=/var/lib/alloy/data /etc/alloy/config.alloy
    ports:
      - "12345:12345"
    networks:
      - observability-net
    depends_on:
      - loki
    restart: unless-stopped

  loadgen:
    image: grafana/k6:0.48.0
    container_name: loadgen
    volumes:
      - ./infra/loadgen/k6:/scripts
    networks:
      - observability-net
    command: ["run", "/scripts/smoke.js"]
    profiles:
      - loadtest

  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      - POSTGRES_DB=buggy
      - POSTGRES_USER=buggy
      - POSTGRES_PASSWORD=buggy
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - observability-net
    profiles:
      - demo
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U buggy"]
      interval: 5s
      timeout: 5s
      retries: 5

  buggy-service:
    build:
      context: ./demo-buggy-service
    container_name: buggy-service
    ports:
      - "8081:8080"
    environment:
      - SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/buggy
      - SPRING_DATASOURCE_USERNAME=buggy
      - SPRING_DATASOURCE_PASSWORD=buggy
      - SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=${HIKARI_MAX_POOL:-10}
    networks:
      - observability-net
    profiles:
      - demo
    depends_on:
      postgres:
        condition: service_healthy

networks:
  observability-net:
    driver: bridge

volumes:
  grafana_data:
  loki_data:
  postgres_data:
```

- [ ] **Step 4: 기존 인프라(no profile)는 영향 없는지 확인**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose config --services
```

Expected output (순서는 다를 수 있음):
```
loki
grafana
alloy
loadgen
postgres
buggy-service
```

- [ ] **Step 5: demo profile만 기동해서 buggy-service 동작 확인**

Run:
```bash
docker compose --profile demo up -d postgres buggy-service
sleep 30
docker compose ps
curl -s http://localhost:8081/actuator/health
```

Expected: postgres `healthy`, buggy-service `running`, health check `{"status":"UP"}`.

- [ ] **Step 6: 시나리오 1 트리거 검증**

Run:
```bash
# 정상 케이스
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/api/users/1/profile
# 실패 케이스
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/api/users/999/profile
```

Expected: 첫 번째 `200`, 두 번째 `500` (NPE).

- [ ] **Step 7: 정리**

Run:
```bash
docker compose --profile demo down
```

- [ ] **Step 8: Commit**

```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
git add .gitmodules demo-buggy-service docker-compose.yml infra/postgres/
git commit -m "feat(docker): add postgres + buggy-service to demo profile via submodule"
```

> `demo-buggy-service` 항목은 submodule pointer만 commit되므로 가벼움.

---

## Task 12: Alloy 설정 확장 — buggy-service 컨테이너 인식

**Files:**
- Modify: `~/Documents/study/demo-log-observability/demo-log-observability/infra/alloy/alloy.hcl`

기존 Alloy 설정은 `.*-app-.*` regex로 컨테이너를 필터링하고 있다. `buggy-service`도 인식하도록 확장.

- [ ] **Step 1: 기존 alloy.hcl 확인**

Run:
```bash
cat ~/Documents/study/demo-log-observability/demo-log-observability/infra/alloy/alloy.hcl
```

Expected: 기존 설정 출력. `discovery.docker`, `discovery.relabel`, `loki.source.docker`, `loki.write` 블록이 있어야 함.

- [ ] **Step 2: alloy.hcl 수정**

`infra/alloy/alloy.hcl`을 다음으로 교체 (기존 설정과 비교해서 변경된 부분: `keep` regex가 `.*(app|buggy-service).*`로 확장됨, label에 `service`도 동적으로 잡음):

```hcl
discovery.docker "containers" {
  host             = "unix:///var/run/docker.sock"
  refresh_interval = "5s"
}

discovery.relabel "docker" {
  targets = discovery.docker.containers.targets

  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(app|buggy-service|demo-app-.*)"
    action        = "keep"
  }

  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(.+)"
    target_label  = "container_name"
  }

  rule {
    target_label = "job"
    replacement  = "spring-boot-demo"
  }

  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/buggy-service"
    target_label  = "service"
    replacement   = "demo-buggy-service"
  }

  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/app|/demo-app-.*"
    target_label  = "service"
    replacement   = "demo-api"
  }

  rule {
    target_label = "env"
    replacement  = "local"
  }
}

loki.source.docker "containers" {
  host       = "unix:///var/run/docker.sock"
  targets    = discovery.relabel.docker.output
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

- [ ] **Step 3: docker compose 재기동 후 검증**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo up -d
sleep 30
# 시나리오 1 트래픽 생성
curl -s http://localhost:8081/api/users/1/profile > /dev/null
curl -s http://localhost:8081/api/users/999/profile > /dev/null
sleep 10
# Loki에서 로그 조회
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
    --data-urlencode 'query={service="demo-buggy-service"}' \
    --data-urlencode "start=$(($(date +%s) - 60))000000000" \
    --data-urlencode "end=$(date +%s)000000000" \
    --data-urlencode "limit=5" | head -c 500
```

Expected: Loki 응답 JSON에 `demo-buggy-service` 로그 라인이 보임.

- [ ] **Step 4: Grafana Explore 수동 검증**

Run:
```bash
open http://localhost:3000   # admin/admin
```

Grafana Explore에서:
```logql
{service="demo-buggy-service"} | json
```

Expected: JSON 파싱된 로그가 보이고 `commit_sha`, `request_id`, `endpoint` 등의 필드 확인 가능.

- [ ] **Step 5: 정리**

Run:
```bash
docker compose --profile demo down
```

- [ ] **Step 6: Commit**

```bash
git add infra/alloy/alloy.hcl
git commit -m "feat(alloy): extend container discovery to include buggy-service with service label"
```

---

## Task 13: Grafana Alert rule + Contact point — webhook 추가

**Files:**
- Modify: `~/Documents/study/demo-log-observability/demo-log-observability/infra/grafana/provisioning/alerting/alerts.yaml`
- Modify: `~/Documents/study/demo-log-observability/demo-log-observability/infra/grafana/provisioning/alerting/contactpoints.yaml`

- [ ] **Step 1: 기존 alerts.yaml 백업 확인**

Run:
```bash
cat ~/Documents/study/demo-log-observability/demo-log-observability/infra/grafana/provisioning/alerting/alerts.yaml
```

Expected: 기존 "High Error Log Rate" rule이 있음.

- [ ] **Step 2: alerts.yaml에 buggy-service용 rule 추가**

기존 파일을 다음으로 교체:

```yaml
apiVersion: 1

groups:
  - orgId: 1
    name: app-errors
    folder: Demo
    interval: 1m
    rules:
      - uid: high-error-log-rate
        title: High Error Log Rate
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: loki
            model:
              datasource:
                type: loki
                uid: loki
              expr: |
                sum(count_over_time({job="spring-boot-demo"} | json | level="ERROR" [5m]))
              intervalMs: 60000
              maxDataPoints: 43200
              refId: A
          - refId: B
            relativeTimeRange:
              from: 0
              to: 0
            datasourceUid: __expr__
            model:
              type: reduce
              expression: A
              reducer: last
              refId: B
              datasource:
                type: __expr__
                uid: __expr__
          - refId: C
            relativeTimeRange:
              from: 0
              to: 0
            datasourceUid: __expr__
            model:
              type: threshold
              expression: B
              conditions:
                - evaluator:
                    params: [50]
                    type: gt
                  operator:
                    type: and
                  query:
                    params: []
                  reducer:
                    params: []
                    type: last
                  type: query
              refId: C
              datasource:
                type: __expr__
                uid: __expr__
        for: 1m
        noDataState: OK
        execErrState: OK
        labels:
          severity: warning

      - uid: ai-bot-buggy-service-error
        title: AI Bot - Buggy Service Error
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: loki
            model:
              datasource:
                type: loki
                uid: loki
              expr: |
                sum by (service, commit_sha) (
                  count_over_time({service="demo-buggy-service"} | json | level="ERROR" [5m])
                )
              intervalMs: 60000
              maxDataPoints: 43200
              refId: A
          - refId: B
            relativeTimeRange:
              from: 0
              to: 0
            datasourceUid: __expr__
            model:
              type: reduce
              expression: A
              reducer: last
              refId: B
              datasource:
                type: __expr__
                uid: __expr__
          - refId: C
            relativeTimeRange:
              from: 0
              to: 0
            datasourceUid: __expr__
            model:
              type: threshold
              expression: B
              conditions:
                - evaluator:
                    params: [10]
                    type: gt
                  operator:
                    type: and
                  query:
                    params: []
                  reducer:
                    params: []
                    type: last
                  type: query
              refId: C
              datasource:
                type: __expr__
                uid: __expr__
        for: 30s
        noDataState: OK
        execErrState: OK
        labels:
          severity: critical
          target: ai-bot
```

> 두 번째 rule은 임계값 10건/5분으로 낮춰서 시연 시 빠르게 발화하도록 함. `commit_sha`, `service` 라벨이 group by로 들어가서 webhook payload `commonLabels`에 자동 포함됨.

- [ ] **Step 3: contactpoints.yaml에 webhook 추가**

기존 파일을 다음으로 교체:

```yaml
apiVersion: 1

contactPoints:
  - orgId: 1
    name: ai-bot-webhook
    receivers:
      - uid: ai-bot-webhook
        type: webhook
        settings:
          url: ${AI_BOT_WEBHOOK_URL}
          httpMethod: POST
          username: ''
          password: ''
          authorization_scheme: Bearer
          authorization_credentials: ${WEBHOOK_TOKEN}
          maxAlerts: 0

policies:
  - orgId: 1
    receiver: grafana-default-email
    group_by: ['grafana_folder', 'alertname']
    routes:
      - receiver: ai-bot-webhook
        object_matchers:
          - ['target', '=', 'ai-bot']
        group_by: ['service', 'commit_sha']
        group_wait: 10s
        group_interval: 30s
        repeat_interval: 1h
```

> Grafana는 provisioning 파일에서 `${...}` 환경변수 치환을 지원한다 (Grafana 9.5+).

- [ ] **Step 4: grafana 컨테이너 환경변수 확인**

기존 docker-compose.yml의 grafana service에는 `AI_BOT_WEBHOOK_URL`, `WEBHOOK_TOKEN`이 없음. 추가해야 함.

`docker-compose.yml`의 `grafana` 섹션을 다음으로 수정 (environment에 2줄 추가):

```yaml
  grafana:
    image: grafana/grafana:10.2.3
    container_name: grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_LOG_LEVEL=info
      - GF_UNIFIED_ALERTING_ENABLED=true
      - GF_ALERTING_ENABLED=false
      - AI_BOT_WEBHOOK_URL=${AI_BOT_WEBHOOK_URL:-http://webhook-echo:9000/webhooks/grafana}
      - WEBHOOK_TOKEN=${WEBHOOK_TOKEN:-dev-token}
    volumes:
      - ./infra/grafana/provisioning:/etc/grafana/provisioning
      - ./infra/grafana/dashboards:/etc/grafana/dashboards
      - grafana_data:/var/lib/grafana
    networks:
      - observability-net
    depends_on:
      - loki
    restart: unless-stopped
```

- [ ] **Step 5: docker compose 재기동 후 alert rule 등록 확인**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo up -d
sleep 30
curl -s -u admin:admin http://localhost:3000/api/v1/provisioning/alert-rules | head -c 1000
```

Expected: 응답에 `ai-bot-buggy-service-error`가 포함됨.

- [ ] **Step 6: 정리**

Run:
```bash
docker compose --profile demo down
```

- [ ] **Step 7: Commit**

```bash
git add infra/grafana/provisioning/alerting/ docker-compose.yml
git commit -m "feat(grafana): add ai-bot webhook contact point + buggy-service alert rule"
```

---

## Task 14: k6 시나리오 스크립트 3개

**Files:**
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/infra/loadgen/k6/scenario-1-npe.js`
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/infra/loadgen/k6/scenario-2-divzero.js`
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/infra/loadgen/k6/scenario-3-enum.js`

- [ ] **Step 1: scenario-1-npe.js**

Create `infra/loadgen/k6/scenario-1-npe.js`:

```javascript
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
```

- [ ] **Step 2: scenario-2-divzero.js**

Create `infra/loadgen/k6/scenario-2-divzero.js`:

```javascript
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
```

- [ ] **Step 3: scenario-3-enum.js**

Create `infra/loadgen/k6/scenario-3-enum.js`:

```javascript
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
```

- [ ] **Step 4: k6 실행 검증 (시나리오 1만)**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo up -d postgres buggy-service alloy loki grafana
sleep 30
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
```

Expected: k6 출력에 `http_req_failed: ~80%` 비슷한 비율이 보임. (의도된 실패)

- [ ] **Step 5: Loki에서 에러 로그 확인**

Run:
```bash
sleep 5
curl -s -G "http://localhost:3100/loki/api/v1/query" \
    --data-urlencode 'query=sum(count_over_time({service="demo-buggy-service"} | json | level="ERROR" [5m]))' | head -c 400
```

Expected: 응답에 숫자 카운트(예: `"value":[...,"50"]`)가 포함되어 임계값(10) 초과.

- [ ] **Step 6: 정리**

Run:
```bash
docker compose --profile demo down
```

- [ ] **Step 7: Commit**

```bash
git add infra/loadgen/k6/scenario-1-npe.js \
        infra/loadgen/k6/scenario-2-divzero.js \
        infra/loadgen/k6/scenario-3-enum.js
git commit -m "feat(loadgen): add k6 scenarios 1-3 for CODE_BUG triggers"
```

---

## Task 15: .env.example + 임시 webhook echo 서버

**Files:**
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/.env.example`
- Create: `~/Documents/study/demo-log-observability/demo-log-observability/tools/webhook-echo/server.py`

이 plan 단계에서는 AI 봇이 아직 없으므로, Grafana Webhook이 진짜로 도착하는지 검증할 echo 서버를 만든다.

- [ ] **Step 1: .env.example 작성**

Create `.env.example`:

```bash
# AI 봇 webhook 수신처 (Plan 1에서는 echo 서버, Plan 2부터 ai-bot 컨테이너)
AI_BOT_WEBHOOK_URL=http://webhook-echo:9000/webhooks/grafana
WEBHOOK_TOKEN=dev-token

# HikariCP 풀 (시나리오 5 시연 시 작게 — Plan 4)
HIKARI_MAX_POOL=10

# 다음 plan들에서 사용
# ANTHROPIC_API_KEY=sk-ant-xxx
# GITHUB_TOKEN=ghp_xxx
# GITHUB_REPO=<owner>/demo-buggy-service
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
# DRY_RUN=false
# DAILY_COST_CAP_USD=5
```

- [ ] **Step 2: webhook echo 서버 작성**

Run:
```bash
mkdir -p ~/Documents/study/demo-log-observability/demo-log-observability/tools/webhook-echo
```

Create `tools/webhook-echo/server.py`:

```python
"""
Plan 1 임시 webhook echo 서버.
Grafana가 보내는 webhook payload를 콘솔과 디스크에 기록한다.
Plan 2부터는 ai-bot이 이 역할을 대체한다.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
from datetime import datetime

LOG_FILE = "/tmp/webhook-echo.log"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        auth = self.headers.get("Authorization", "")

        record = {
            "received_at": datetime.utcnow().isoformat() + "Z",
            "path": self.path,
            "authorization": auth,
            "body": json.loads(body) if body else None,
        }

        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, format, *args):
        # 기본 access log 끔 (우리 record가 더 자세함)
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    httpd = HTTPServer(("0.0.0.0", port), Handler)
    print(f"webhook-echo listening on :{port}", flush=True)
    httpd.serve_forever()
```

- [ ] **Step 3: docker-compose에 webhook-echo 서비스 추가**

`docker-compose.yml`의 services 끝에 추가 (volumes 블록 직전):

```yaml
  webhook-echo:
    image: python:3.12-alpine
    container_name: webhook-echo
    working_dir: /app
    volumes:
      - ./tools/webhook-echo:/app
    command: ["python", "server.py"]
    ports:
      - "9000:9000"
    networks:
      - observability-net
    profiles:
      - demo
```

- [ ] **Step 4: 전체 풀세트 기동**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
cp .env.example .env
docker compose --profile demo up -d
sleep 30
docker compose ps
```

Expected: 모든 컨테이너(loki, grafana, alloy, postgres, buggy-service, webhook-echo)가 `Up`/`healthy`.

- [ ] **Step 5: webhook echo 동작 단독 검증**

Run:
```bash
curl -X POST http://localhost:9000/webhooks/grafana \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer dev-token" \
    -d '{"test":"hello"}'
echo
docker compose logs webhook-echo | tail -5
```

Expected: 응답 `{"ok":true}`, 컨테이너 로그에 받은 record JSON 출력.

- [ ] **Step 6: Commit**

```bash
git add .env.example tools/webhook-echo/ docker-compose.yml
git commit -m "feat(tools): add webhook-echo for Plan 1 validation + .env.example"
```

> `.env`는 `.gitignore`에 이미 등록되어 있을 것 (기존 PROJECT 셋업 시). 확인하고 없으면 추가.

- [ ] **Step 7: .gitignore에 .env 등록 확인**

Run:
```bash
grep -E "^\.env$|^\.env\b" ~/Documents/study/demo-log-observability/demo-log-observability/.gitignore
```

Expected: `.env` 매칭 라인 출력. 없으면 다음을 추가:

```bash
echo ".env" >> ~/Documents/study/demo-log-observability/demo-log-observability/.gitignore
git add .gitignore
git commit -m "chore: ignore .env"
```

---

## Task 16: End-to-end Plan 1 동작 검증 + 최종 commit

**Files:** (변경 없음, 검증 + 문서 갱신)
- Modify: `~/Documents/study/demo-log-observability/demo-log-observability/README.md` (Plan 1 섹션 추가)

- [ ] **Step 1: 전체 풀세트 기동**

Run:
```bash
cd ~/Documents/study/demo-log-observability/demo-log-observability
docker compose --profile demo up -d --build
sleep 60
docker compose ps
```

Expected: 모든 컨테이너 `Up`/`healthy`.

- [ ] **Step 2: 시나리오 1 트리거 + Loki 로그 확인**

Run:
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js
sleep 30
# Loki에서 에러 카운트
curl -s -G "http://localhost:3100/loki/api/v1/query" \
    --data-urlencode 'query=sum(count_over_time({service="demo-buggy-service"} | json | level="ERROR" [5m]))' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('error count:', d['data']['result'])"
```

Expected: error count > 10.

- [ ] **Step 3: Grafana Alert 발화 확인 + webhook 도착 확인**

Run:
```bash
# 1분간 대기 (alert "for: 30s" + 평가 사이클)
sleep 90
# Grafana alert 상태
curl -s -u admin:admin "http://localhost:3000/api/v1/provisioning/alert-rules" \
    | python3 -c "import sys,json; rules=json.load(sys.stdin); [print(r['title']) for r in rules]"
# webhook-echo 로그 확인
docker compose logs webhook-echo | tail -20
```

Expected:
- Grafana alert rule "AI Bot - Buggy Service Error" 등록 확인
- webhook-echo 로그에 Grafana가 보낸 payload JSON 출력. `commonLabels.service = "demo-buggy-service"`, `commonLabels.commit_sha = "<sha>"` 등 포함.

> Alert 발화는 평가 사이클이 필요하므로 1~2분 더 기다려야 할 수도 있다. 안 보이면 추가로 시나리오를 한 번 더 트리거.

- [ ] **Step 4: 시나리오 2/3도 동일하게 검증**

Run:
```bash
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-2-divzero.js
sleep 60
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-3-enum.js
sleep 60
docker compose logs webhook-echo | tail -30
```

Expected: webhook-echo에 추가 record들이 도착함.

- [ ] **Step 5: 정리**

Run:
```bash
docker compose --profile demo down
docker compose --profile demo down -v   # 볼륨까지 정리 (선택)
```

- [ ] **Step 6: README에 Plan 1 동작 검증 섹션 추가**

기존 `README.md` 끝(또는 적절한 위치)에 다음 섹션 추가:

```markdown
## AI Incident Bot 데모 (Plan 1)

### 실행

```bash
cp .env.example .env
# (선택) GitHub submodule 미가져온 경우
git submodule update --init --recursive

docker compose --profile demo up -d --build
```

### 시나리오 트리거

```bash
# 시나리오 1 (NPE)
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-1-npe.js

# 시나리오 2 (0 나눗셈)
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-2-divzero.js

# 시나리오 3 (Enum 매핑)
docker compose --profile loadtest run --rm loadgen run /scripts/scenario-3-enum.js
```

### 검증

- Grafana: http://localhost:3000 (admin/admin) → Explore → `{service="demo-buggy-service"} | json | level="ERROR"`
- Webhook 수신 확인: `docker compose logs webhook-echo`
- buggy-service health: http://localhost:8081/actuator/health

Plan 2부터는 webhook-echo가 실제 AI 봇으로 교체된다.
```

- [ ] **Step 7: Final commit**

```bash
git add README.md
git commit -m "docs: add Plan 1 demo execution and trigger guide to README"
```

- [ ] **Step 8: Plan 1 완료 검증**

전체 흐름을 처음부터 다시 한 번 실행:

```bash
# 0. 완전 정리
docker compose --profile demo down -v
docker volume prune -f

# 1. 풀 기동
cp .env.example .env
docker compose --profile demo up -d --build
sleep 90

# 2. 모든 시나리오 트리거
for s in scenario-1-npe scenario-2-divzero scenario-3-enum; do
    docker compose --profile loadtest run --rm loadgen run /scripts/$s.js
done

# 3. 검증
sleep 60
echo "=== Loki error count ==="
curl -s -G "http://localhost:3100/loki/api/v1/query" \
    --data-urlencode 'query=sum(count_over_time({service="demo-buggy-service"} | json | level="ERROR" [10m]))' | head -c 200
echo

echo "=== Webhook echo records ==="
docker compose logs webhook-echo | grep -c '"received_at"'

# 4. 정리
docker compose --profile demo down
```

Expected:
- Loki error count > 30 (3 시나리오 합산)
- Webhook echo records ≥ 1 (Grafana alert가 발화해서 webhook 호출됨)

이 단계가 통과하면 Plan 1 완료.

---

## Plan 1 Out of Scope

다음 항목들은 이 plan에서 다루지 않는다 (Plan 2~4에서 처리).

- AI 봇 (ai-bot 디렉토리) — Plan 2
- Loki LogQL → AI 봇 자동 조회 — Plan 2
- Git worktree 관리 — Plan 2
- Claude Agent SDK 통합 — Plan 3
- GitHub Issue/PR 자동 생성 — Plan 3
- Slack 알림 — Plan 2/3
- 시나리오 4 (DATA_ANOMALY), 5 (INFRA_ISSUE), 6 (BENIGN_ERROR) — Plan 4
- 봇 자체 Grafana 대시보드 — Plan 4
- DEMO_GUIDE.md — Plan 4

---

## Plan 1 완료 시 산출물

- 새 GitHub 레포 `demo-buggy-service` (3개 시나리오 tag 포함)
- demo-log-observability에 submodule로 마운트
- `docker compose --profile demo up -d` 한 줄로 모든 서비스 기동
- 시나리오 1~3 트리거 시 Loki에 정상 적재 + Grafana Alert 발화 + Webhook 호출
- 임시 webhook echo로 Grafana payload 검증 가능
