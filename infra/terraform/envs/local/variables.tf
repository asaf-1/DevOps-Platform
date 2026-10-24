variable "localstack_endpoint" {
  description = "LocalStack edge endpoint. Host: http://localhost:4566. Devcontainer: http://host.docker.internal:4566. In cluster: http://localstack.localstack.svc.cluster.local:4566."
  type        = string
  default     = "http://localhost:4566"
}

variable "kubeconfig_path" {
  description = "Kubeconfig for the kubernetes provider. Leave null in the cluster (in-cluster credentials) or when KUBE_CONFIG_PATH is set."
  type        = string
  default     = null
}
