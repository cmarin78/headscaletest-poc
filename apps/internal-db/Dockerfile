FROM postgres:16-alpine

COPY init.sql /docker-entrypoint-initdb.d/

ENV POSTGRES_DB=headscaletest
ENV POSTGRES_USER=headscaletest
ENV POSTGRES_PASSWORD=headscaletest