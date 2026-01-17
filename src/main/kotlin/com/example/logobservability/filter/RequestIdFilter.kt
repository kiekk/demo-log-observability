package com.example.logobservability.filter

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
class RequestIdFilter : OncePerRequestFilter() {

    private val logger = LoggerFactory.getLogger(javaClass)

    override fun doFilterInternal(
        request: HttpServletRequest,
        response: HttpServletResponse,
        filterChain: FilterChain
    ) {
        val requestId = UUID.randomUUID().toString()
        val startTime = System.currentTimeMillis()

        try {
            // Set MDC fields
            MDC.put("request_id", requestId)
            MDC.put("endpoint", request.requestURI)
            MDC.put("method", request.method)

            // Process request
            filterChain.doFilter(request, response)

        } finally {
            val elapsedMs = System.currentTimeMillis() - startTime
            val status = response.status

            // Add additional MDC fields for summary log
            MDC.put("status", status.toString())
            MDC.put("elapsed_ms", elapsedMs.toString())

            // Log request summary
            logger.info("Request completed")

            // Clear MDC
            MDC.clear()
        }
    }
}
