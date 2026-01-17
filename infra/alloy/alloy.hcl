// Discover Docker containers
discovery.docker "containers" {
  host = "unix:///var/run/docker.sock"
  refresh_interval = "5s"
}

// Relabel discovered containers
discovery.relabel "docker" {
  targets = discovery.docker.containers.targets

  // Only collect logs from app container
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex = ".*-app-.*"
    action = "keep"
  }

  // Set job label
  rule {
    target_label = "job"
    replacement = "spring-boot-demo"
  }

  // Set service label
  rule {
    target_label = "service"
    replacement = "demo-api"
  }

  // Set env label
  rule {
    target_label = "env"
    replacement = "local"
  }

  // Set container name label
  rule {
    source_labels = ["__meta_docker_container_name"]
    target_label = "container"
  }
}

// Collect logs from Docker
loki.source.docker "app" {
  host = "unix:///var/run/docker.sock"
  targets = discovery.relabel.docker.output
  forward_to = [loki.write.default.receiver]
  relabel_rules = discovery.relabel.docker.rules
}

// Write logs to Loki
loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
