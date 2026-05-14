# CI/CD

Текущий статус на 2026-05-14:

- базовый workflow [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) уже заведен;
- A-06 больше не `TODO`: PR/push CI теперь запускает install/syntax sanity, обязательные `ruff` и `mypy` для canonical runtime и `pytest`;
- реальный merge gate сейчас: зелёный GitHub Actions CI + ручная smoke-проверка server runtime после деплоя.

Ниже описано текущее состояние и ближайшее целевое развитие CI/CD.

GitHub Actions для CI. Self-hosted runner на server runtime или выделенном dev-host для тяжёлых integration-тестов (опц.).

## Workflows

### `.github/workflows/ci.yml` (уже активно для PR и push в `main`)

1. checkout
2. setup-python with built-in pip cache (`actions/setup-python`)
3. install/syntax sanity job на Python 3.12 (`pip check` + `compileall`)
4. обязательный `ruff`-job по canonical runtime через `make lint-runtime`
5. обязательный `mypy`-job по canonical runtime через `make typecheck-runtime`
6. test matrix на Python 3.12 и 3.13
7. upload `pytest` JUnit artifacts

Gate: все шаги зелёные → merge разрешён.

Best practices, которые уже применены:

- workflow-level `concurrency` с `cancel-in-progress`;
- pip cache через `setup-python`, а не отдельный `actions/cache`;
- отдельный быстрый preflight job перед test matrix;
- `fail-fast: false` для matrix, чтобы видеть все сломанные версии Python;
- артефакты `pytest` загружаются даже при падении тестов (`if: always()`).

### Ближайшее развитие `ci.yml`

Следующие итерации для этого же workflow:

1. integration split c testcontainers
2. расширить `mypy` gate с canonical runtime на transitional/runtime-adjacent пакеты после погашения оставшегося static-analysis debt
3. coverage upload
4. `pip-audit`
5. schema/contract drift checks
6. docs build/lint

### `.github/workflows/build-images.yml` (на merge в main)

Пока ещё не реализован.

1. `docker buildx bake --push` для всех сервисов
2. push в целевой registry (`ghcr.io` или другой выбранный registry)
3. tag: `git sha`, `latest`, `vX.Y.Z` если на тэге

### `.github/workflows/deploy.yml` (вручную, через GitHub Actions environment `production`)

Уже реализован как manual deploy workflow.

1. запуск только через `workflow_dispatch`
2. обязательное подтверждение `confirm_production=true`
3. serial rollout через workflow-level `concurrency` без `cancel-in-progress`
4. SSH на текущий server runtime
5. запуск `scripts/deploy/remote-deploy.sh <ref>`
6. `git fetch` + `git checkout` + `git pull --ff-only`
7. `docker compose build` для canonical runtime и `migration-runner`
8. `docker compose up -d --wait` для data-layer
9. `migration-runner upgrade head`
10. `docker compose up -d --wait` для app-layer
11. финальный smoke-check по `mcp-rest-api /healthz`

Best practices, которые уже применены:

- manual production deploy не запускается автоматически на каждый merge;
- защищённый `environment` для production secrets/vars;
- подтверждение деплоя отдельным boolean input;
- serial execution через `concurrency`, чтобы не пересекались два деплоя;
- миграции выполняются из отдельного containerized `migration-runner`, а не из случайного app-container.

### `.github/workflows/nightly.yml`

Пока ещё не реализован.

1. e2e long-suite
2. load test (50 msg/sec sustained 10 min)
3. backup restore-drill
4. dependency updates check
5. отчёт в `docs/09-roadmap/milestones.md` секцию «Nightly results»

## Локальные хуки

`.pre-commit-config.yaml`:

- ruff (check + format)
- mypy (только staged)
- biome / eslint (UI staged)
- gitleaks
- check-yaml, check-json, end-of-file-fixer, trailing-whitespace
- check-merge-conflict
- forbid-large-files

Установка: `pre-commit install` сразу после клона полного checkout.

## Версионирование релизов

- Semver: `vMAJOR.MINOR.PATCH`.
- Тэг — на merged PR с label `release`.
- Changelog генерится из conventional commits через `git-cliff`.

## Артефакты

- Docker images — `ghcr.io/<org>/pil-<service>:<sha>`.
- OpenAPI — отдельный артефакт `openapi-vX.Y.Z.yaml` в release-assets.
- Контракты — `contracts-vX.Y.Z.zip`.

## Бранч-стратегия

- Транк-based: `main` всегда стабилен.
- Hot-fix: `fix/...` → быстро в `main`.
- Release ветки не используем (один продакшен — домашний Proxmox).

## Code Owners

- `CODEOWNERS` файл (когда репо станет публичным или мульти-юзерским). В однопользовательском режиме — `* @owner`.
- Любые `libs/contracts/**` и `migrations/**` — требуют двойной review (agent + человек).

## Cache & speed

- buildx caches на ghcr.io / локально.
- poetry cache reused.
- npm pnpm-store reused.
- Integration runs с заранее прогретыми testcontainer-volumes (опц., через `--reuse`).

## Метрики CI

- Длительность пайплайна — цель P50 ≤ 7 мин.
- Flaky tests — > 1% retry rate отслеживается, тест переходит в quarantine.

## Деплой через PR

Каждый merge в `main` автоматически:
1. Билдит docker images с тэгом sha.
2. Открывает PR в репозиторий `pil-ops` (если выделим) с обновлёнными image tags + helm values.
3. Owner мерджит — деплой триггерится.

Для MVP-1 — упрощённый flow: обновить runtime-дерево, выполнить `docker compose ... up -d`, затем ручной smoke-check.
