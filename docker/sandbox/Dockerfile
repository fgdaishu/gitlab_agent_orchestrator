FROM node:22-bookworm

ARG DEBIAN_FRONTEND=noninteractive
ARG OPENCODE_NPM_PACKAGE=opencode-ai
ARG CODEX_NPM_PACKAGE=@openai/codex
ARG GEMINI_NPM_PACKAGE=@google/gemini-cli
ARG INSTALL_OPENCODE=true
ARG INSTALL_CODEX=true
ARG INSTALL_GEMINI=true

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        less \
        openssh-client \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    npm config set fund false; \
    npm config set audit false; \
    if [ "${INSTALL_OPENCODE}" = "true" ]; then npm install -g "${OPENCODE_NPM_PACKAGE}"; fi; \
    if [ "${INSTALL_CODEX}" = "true" ]; then npm install -g "${CODEX_NPM_PACKAGE}"; fi; \
    if [ "${INSTALL_GEMINI}" = "true" ]; then npm install -g "${GEMINI_NPM_PACKAGE}"; fi; \
    npm cache clean --force

RUN useradd --create-home --shell /bin/bash agent \
    && mkdir -p /workspace /home/agent/.cache /home/agent/.config \
    && chown -R agent:agent /workspace /home/agent

USER agent
WORKDIR /workspace

ENV HOME=/home/agent
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
ENV NO_PROXY=localhost,127.0.0.1,::1

RUN set -eux; \
    git --version; \
    node --version; \
    npm --version; \
    python3 --version; \
    rg --version >/dev/null; \
    if [ "${INSTALL_OPENCODE}" = "true" ]; then command -v opencode; fi; \
    if [ "${INSTALL_CODEX}" = "true" ]; then command -v codex; fi; \
    if [ "${INSTALL_GEMINI}" = "true" ]; then command -v gemini; fi

CMD ["sh", "-lc", "sleep infinity"]
