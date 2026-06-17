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
