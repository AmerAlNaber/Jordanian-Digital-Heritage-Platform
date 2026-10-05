# MinIO server and client built from their pinned source releases (ADR-0003). MinIO withdrew its
# container images from the public registries in 2025; the platform keeps the specified
# S3-compatible store by building the same software from source, pinned by release tag.
#
# Upstream stopped releasing before several of its Go dependencies received security fixes, so
# the build raises those modules to the fixed versions Trivy names before compiling (SEC-18). The
# list is reviewed whenever the image scan reports a new fixed finding. Both programs compile and
# pass their own module resolution with these versions; the toolchain is the one the raised
# modules require.
FROM golang:1.26-bookworm AS build
ARG MINIO_RELEASE=RELEASE.2025-10-15T17-29-55Z
ARG MC_RELEASE=RELEASE.2025-08-13T08-35-41Z
ENV CGO_ENABLED=0 GOFLAGS="-trimpath -mod=mod" GOTOOLCHAIN=local
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git /src/minio \
    && cd /src/minio \
    && go get google.golang.org/grpc@v1.83.2 \
              golang.org/x/crypto@v0.57.0 golang.org/x/net@v0.59.0 golang.org/x/text@v0.42.0 \
              github.com/prometheus/prometheus@v0.311.3 github.com/apache/thrift@v0.24.0 \
              github.com/buger/jsonparser@v1.1.2 github.com/go-jose/go-jose/v4@v4.1.4 \
              github.com/rabbitmq/amqp091-go@v1.13.0 go.opentelemetry.io/otel/sdk@v1.47.0 \
    && go build -ldflags "-s -w" -o /out/minio .
RUN git clone --depth 1 --branch "${MC_RELEASE}" https://github.com/minio/mc.git /src/mc \
    && cd /src/mc \
    && go get google.golang.org/grpc@v1.83.2 \
              golang.org/x/crypto@v0.57.0 golang.org/x/net@v0.59.0 golang.org/x/text@v0.42.0 \
              github.com/prometheus/prometheus@v0.311.3 \
    && go build -ldflags "-s -w" -o /out/mc .

FROM debian:bookworm-slim
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10004 --create-home minio \
    && mkdir -p /data && chown minio:minio /data
COPY --from=build /out/minio /out/mc /usr/local/bin/
USER minio
VOLUME /data
EXPOSE 9000 9001
HEALTHCHECK --interval=10s --timeout=5s --retries=30 CMD curl -fsS http://localhost:9000/minio/health/live || exit 1
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
