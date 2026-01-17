package com.example.logobservability.controller

import org.slf4j.LoggerFactory
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import kotlin.random.Random

@RestController
@RequestMapping("/api")
class ApiController {

    private val logger = LoggerFactory.getLogger(javaClass)

    @GetMapping("/hello")
    fun hello(): ResponseEntity<Map<String, String>> {
        logger.info("Processing hello request")
        return ResponseEntity.ok(
            mapOf(
                "message" to "Hello from Demo API",
                "status" to "ok"
            )
        )
    }

    @GetMapping("/slow")
    fun slow(@RequestParam(defaultValue = "200") ms: Long): ResponseEntity<Map<String, Any>> {
        logger.info("Processing slow request with delay: ${ms}ms")

        Thread.sleep(ms)

        logger.info("Completed slow request after ${ms}ms")
        return ResponseEntity.ok(
            mapOf(
                "message" to "Slow request completed",
                "delay_ms" to ms
            )
        )
    }

    @GetMapping("/error")
    fun error(@RequestParam(defaultValue = "0.1") rate: Double): ResponseEntity<Map<String, Any>> {
        val shouldError = Random.nextDouble() < rate

        return if (shouldError) {
            logger.error("Error occurred! Random error triggered by rate: $rate")
            ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(
                mapOf(
                    "message" to "Internal server error",
                    "error" to "Random error triggered",
                    "rate" to rate
                )
            )
        } else {
            logger.info("Error endpoint called but no error triggered (rate: $rate)")
            ResponseEntity.ok(
                mapOf(
                    "message" to "Success",
                    "rate" to rate
                )
            )
        }
    }

    @GetMapping("/burst")
    fun burst(@RequestParam(defaultValue = "100") lines: Int): ResponseEntity<Map<String, Any>> {
        logger.info("Processing burst request with $lines log lines")

        repeat(lines) { i ->
            when {
                i % 10 == 0 -> logger.warn("Burst log line $i - WARNING level")
                i % 5 == 0 -> logger.info("Burst log line $i - INFO level")
                else -> logger.debug("Burst log line $i - DEBUG level")
            }
        }

        logger.info("Completed burst request with $lines log lines")
        return ResponseEntity.ok(
            mapOf(
                "message" to "Burst completed",
                "lines_generated" to lines
            )
        )
    }
}
