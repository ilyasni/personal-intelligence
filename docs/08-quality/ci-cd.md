# CI/CD

Статус на 2026-05-19:

- базовый workflow [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) активен для PR, `main` и `workflow_dispatch`;
- deploy workflow [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) активен как ручной production rollout;
- image workflow [`.github/workflows/build-images.yml`](../../.github/workflows/build-images.yml) активен для build-only на PR и build+push в GHCR на `main`;
- реальный merge gate сейчас: зелёный GitHub Actions CI + ручной server smoke после runtime-деплоя.

Ниже описан текущий рабочий контур, а не целевое когда-нибудь потом.

## Workflows

### `.github/workflows/ci.yml`

Назначение:

1. checkout
2. `actions/setup-python` с built-in pip cache
3. install / syntax sanity на Python 3.12
4. обязательный `ruff` gate по canonical runtime
5. обязательный `mypy` gate по canonical runtime
6. `pytest` matrix на Python 3.12 и 3.13
7. upload JUnit artifacts

Best practices:

- workflow-level `concurrency` с `cancel-in-progress`
- отдельный быстрый preflight job перед test matrix
- `fail-fast: false` для matrix
- upload test artifacts даже при падении тестов
- минимальные workflow permissions (`contents: read`)

### `.github/workflows/build-images.yml`

Назначение:

1. build-only на `pull_request`
2. build + push в `ghcr.io` на `push` в `main`
3. ручной запуск через `workflow_dispatch` с `push_images=true|false`

Покрываемые образы:

- `pil-xray`
- `pil-telegram-ingestor`
- `pil-ai-orchestrator`
- `pil-memory-projector`
- `pil-embedding-indexer`
- `pil-maintenance`
- `pil-migration-runner`
- `pil-mcp-rest-api`

Best practices:

- `actions/checkout` + Path context вместо Git context, потому что у нас монорепо и build должен видеть локальные файлы checkout-а;
- `docker/setup-buildx-action` как recommended baseline для cache/export features;
- `docker/login-action` в GHCR через `GITHUB_TOKEN`, без отдельных registry secrets;
- `docker/metadata-action` для tag/label generation;
- `cache-from/cache-to: type=gha` с отдельным `scope` на сервис;
- workflow-level `concurrency` с `cancel-in-progress`.

Теги:

- branch / PR refs
- `sha-...`
- `latest` для default branch через `flavor=latest=auto`

### `.github/workflows/deploy.yml`

Назначение:

1. запуск только через `workflow_dispatch`
2. обязательное подтверждение `confirm_production=true`
3. serial rollout через workflow-level `concurrency`
4. SSH на production runtime
5. запуск `scripts/deploy/remote-deploy.sh <ref>`

Production path:

1. `git fetch`
2. `git checkout`
3. `git pull --ff-only`
4. `docker compose build` для canonical runtime и `migration-runner`
5. `docker compose up -d --wait` для data-layer
6. `migration-runner upgrade head`
7. `docker compose up -d --wait` для app-layer
8. финальный smoke-check по `mcp-rest-api /healthz`

Best practices:

- deploy не запускается автоматически на каждый merge
- production secrets/vars живут в GitHub Environment
- deploy подтверждается отдельным boolean input
- миграции идут через отдельный containerized `migration-runner`

### `.github/workflows/nightly.yml`

Пока ещё не реализован.

План:

1. long e2e suite
2. dependency audit
3. restore drill
4. contract/schema drift checks
5. nightly report

## Локальные хуки

`.pre-commit-config.yaml` должен закрывать:

- `ruff check`
- `ruff format`
- `mypy` на staged/runtime-critical code
- `gitleaks`
- `check-yaml`
- `check-json`
- `end-of-file-fixer`
- `trailing-whitespace`
- `check-merge-conflict`

Установка:

```bash
pre-commit install
```

## Артефакты

- Docker images: `ghcr.io/<org>/pil-<service>:<tag>`
- OpenAPI: отдельный release artifact, когда появится formal release flow
- contracts bundle: отдельный artifact, когда contracts станут release-managed

## Версионирование

- SemVer: `vMAJOR.MINOR.PATCH`
- changelog: из conventional commits / release notes
- пока фактический runtime-tagging ведётся через `runtime-vX.Y.Z` в roadmap/releases

## Branch strategy

- trunk-based development
- `main` должен оставаться стабильным
- hotfix-ветки допустимы, но без отдельной долгоживущей release branch модели

## CI metrics

- целевой P50 pipeline time: не больше 7 минут для обычного PR
- flaky tests: всё, что стабильно требует retry, должно либо чиниться, либо уходить в quarantine
- build-image pipeline не должен быть merge blocker для docs-only правок, поэтому он ограничен `paths`

## Next steps

1. расширить `mypy` gate с canonical runtime на оставшиеся runtime-adjacent пакеты
2. добавить coverage upload
3. добавить `pip-audit`
4. formalize release assets и release notes
5. добавить nightly workflow
