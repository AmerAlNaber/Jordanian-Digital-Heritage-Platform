# Keycloak with the platform's extensions (infra/keycloak/extensions) and login theme.
# The build stage compiles and tests the extensions; the runtime stage is the upstream image
# with the provider jar in place and an optimized server build for the options Compose passes.
FROM maven:3.9.9-eclipse-temurin-21 AS extensions
WORKDIR /build
COPY extensions/pom.xml ./
RUN mvn -q -B dependency:go-offline
COPY extensions/src ./src
RUN mvn -q -B package

# Pinned to the release that pom.xml compiles against (keycloak.version).
FROM quay.io/keycloak/keycloak:26.7.5
COPY --from=extensions /build/target/jdhp-keycloak-extensions.jar /opt/keycloak/providers/
COPY theme/jdhp /opt/keycloak/themes/jdhp
ENV KC_DB=postgres \
    KC_HTTP_RELATIVE_PATH=/auth \
    KC_HEALTH_ENABLED=true
RUN /opt/keycloak/bin/kc.sh build
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
