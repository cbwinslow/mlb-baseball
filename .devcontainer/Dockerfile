FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV CHADWICK_REF=baa7c4b3e89cf2c9871a9f7f853f6980b4226af7

# Install OS dependencies, PostgreSQL client, and build tools for Chadwick
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-16 \
    autoconf \
    automake \
    libtool \
    build-essential \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build and install Chadwick Baseball Bureau tools (cwevent, cwgame, cwbox)
RUN git clone https://github.com/chadwickbureau/chadwick.git /tmp/chadwick \
    && cd /tmp/chadwick \
    && git checkout "${CHADWICK_REF}" \
    && autoreconf -i \
    && ./configure --prefix=/usr/local \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/chadwick

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
