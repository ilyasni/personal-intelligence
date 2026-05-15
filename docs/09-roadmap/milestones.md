# Milestones

Сквозной трек прогресса по PIL после AI architecture reset.

## Текущая фаза

`Canonical AI runtime, sprint 7` — базовый extractor-based pipeline заменяется canonical runtime из `telegram-ingestor` + `ai-orchestrator` + `memory-projector` + `embedding-indexer` + `mcp-rest-api` + `maintenance`.

## Доска

| ID | Тикет | Слой | Статус | Owner | Артефакт | Заметки |
|---|---|---|---|---|---|---|
| A-01 | Monorepo init | A | DONE | claude | docs-v0.2.0 | |
| A-02 | `libs/contracts` baseline | A | DONE | claude | docs-v0.2.0 | |
| A-03 | `libs/observability` | A | DONE | claude | docs-v0.2.0 | functional, test debt remains |
| A-04 | `libs/storage-clients` | A | DONE | claude | docs-v0.2.0 | functional, test debt remains |
| A-05 | Compose stack | A | DONE | claude | infra-v0.1.0 | postgres / redis / neo4j / qdrant |
| A-06 | CI workflow | A | DONE | codex | runtime-v1.0.4 | GitHub Actions PR/push CI: install/syntax sanity + canonical-runtime ruff/mypy gates + pytest matrix 3.12/3.13 + junit artifacts |
| A-07 | ADR baseline | A | DRAFT | - | - | |
| B-01 | Core migrations | B | DONE | claude | db-v0.3.0 | |
| B-02 | Interaction / task / audit tables | B | DONE | claude | db-v0.5.0 | |
| B-03 | Seed / fixtures | B | DONE | codex | runtime-v1.0.3 | deterministic fixture generator + committed tests/fixtures bundle + SQL seed reference |
| B-04 | `maintenance` | B | DONE | codex | ops-v0.7.0 | future partitions + processed_event retention |
| C-01 | `telegram-ingestor` | C | DONE | claude | ingest-v0.4.0 | polling via xray |
| D-01 | `entity-extractor` | D | DONE | claude | extract-v0.5.0 | transitional runtime only |
| D-02 | `persona-builder` | D | DONE | claude | persona-v0.6.0 | transitional runtime only |
| D-03 | `task-extractor` | D | DONE | codex | task-v0.7.0 | transitional runtime only |
| D-04 | `chat-summarizer` | D | DONE | codex | summary-v0.8.0 | transitional runtime only |
| X-01 | AI architecture reset | X | DONE | codex | arch-v0.9.0 | ADR-0007 + canonical docs |
| X-02 | `ai-orchestrator` | X | DONE | codex | runtime-v1.0.0 | LangGraph orchestration + deterministic preprocessing + evidence-backed analysis |
| X-03 | Provider policy / routing | X | DONE | codex | runtime-v1.0.0 | Wormsoft primary, Polza fallback, first-wave policy integrated into `ai-orchestrator` |
| X-04 | `embedding-indexer` | X | DONE | codex | runtime-v1.0.0 | Wormsoft embedding probe + alias-based Qdrant bootstrap |
| X-05 | `memory-projector` | X | DONE | codex | runtime-v1.0.0 | Postgres canonical writes + Neo4j projection + embedding jobs |
| E-01 | `mcp-rest-api` baseline | E | DONE | codex | runtime-v1.0.0 | grounded retrieval endpoints + reprocess endpoint |
| E-02 | Analytics layer v1 | E | DONE | codex | runtime-v1.0.0 | overview, conversations, basic HTML UI |
| E-03 | Admin UI baseline | E | DONE | codex | runtime-v1.1.0 | multi-page operator UI with overview, conversations, tasks, people, chats, operator actions, detail drill-downs, flash UX, person block controls, and direct LAN entrypoint |
| E-04 | Person manual tags and notes | E | DONE | codex | runtime-v1.1.3 | canonical `person.manual_tags` + owner comment editing in admin UI, plus filtering by manual tag for segmentation |
| E-05 | Owner identity reset | E | DONE | codex | runtime-v1.1.4 | owner separated from ordinary people UX, new `/admin/me`, people list treated as external-only, docs updated toward `owner_profile` + `relationship_annotation` target model |
| F-01 | Cutover verification | F | DONE | codex | runtime-v1.0.1 | canonical compose live on server, smoke strict green, cutover audit green, orphan groups absent |
| F-02 | Deploy automation | F | DONE | codex | runtime-v1.0.5 | manual GitHub Actions deploy + remote rollout script + containerized migration-runner |

## Sprint history

| Sprint | Date | Closed tickets | Highlights | Lessons |
|---|---|---|---|---|
| sprint-0 | 2026-05-11 | A-01..A-05, B-01 | monorepo + stack + DB baseline | |
| sprint-1 | 2026-05-11 | C-01 | telegram-ingestor live | RU ISP constraints force polling through xray |
| sprint-2 | 2026-05-11 | B-02, D-01 | entity extraction live | |
| sprint-3 | 2026-05-11 | D-02 | persona aggregation live | |
| sprint-4 | 2026-05-12 | D-03, B-04 | tasks + maintenance baseline | backlog noise required safer consumer-group startup |
| sprint-5 | 2026-05-12 | D-04 | hybrid chat summarization live | server runtime needed manual contract sync |
| sprint-6 | 2026-05-13 | X-01 | architecture reset | old extractor split became transitional |
| sprint-7 | 2026-05-13 | X-02..X-05, E-01, E-02 | canonical AI runtime implemented | Context7 verification is now mandatory for infra-facing implementation blocks |
| sprint-8 | 2026-05-14 | F-01 | server cutover verified | CRLF-safe audit scripts and idempotent orphan cleanup simplified remote ops |
| sprint-9 | 2026-05-14 | A-06 | baseline CI activated | GitHub Actions now covers sanity checks, canonical-runtime lint, and tests before merge |
| sprint-10 | 2026-05-14 | B-03 | deterministic fixtures online | committed seed bundle now backs tests, demos, and smoke tooling |
| sprint-11 | 2026-05-14 | A-06 follow-up | canonical-runtime mypy gate activated | `mypy_path` + typed client wrappers removed false-positive noise from src-layout packages |
| sprint-12 | 2026-05-14 | F-02 | deploy automation online | manual production deploy is now codified and repeatable via GitHub Actions + remote script |
| sprint-13 | 2026-05-14 | E-03 | admin UI baseline online | FastAPI templates/static replaced inline analytics HTML with a navigable operator console |
| sprint-14 | 2026-05-14 | E-03 follow-up | operator actions online | detail pages, reprocess flow, task status updates, and chat allowlist toggles made the admin UI operational |
| sprint-15 | 2026-05-14 | E-03 stabilization | live detail pages verified on server | Postgres/Neo4j shape mismatches were fixed and admin UX flows now pass end-to-end smoke on runtime |
| sprint-16 | 2026-05-14 | E-03 UX follow-up | privacy controls and flash feedback online | operator actions now acknowledge success states and person block/unblock is exposed as a real admin control |
| sprint-17 | 2026-05-14 | E-03 access follow-up | direct LAN admin entrypoint online | mcp-rest-api now redirects `/` to `/admin` and can be published to `http://192.168.31.165` without SSH tunneling |
| sprint-18 | 2026-05-14 | E-03 data recovery | admin data restored from Redis history | empty admin root cause was missing canonical backfill, so `ai-orchestrator.backfill` and an ops runbook were added |
| sprint-19 | 2026-05-15 | E-03 localization follow-up | owner identity normalized and AI outputs moved to Russian-first mode | legacy English task data required a one-time cleanup pass in addition to pipeline fixes |
| sprint-20 | 2026-05-15 | E-04 | manual person tags and owner comments online | canonical segmentation works best when tags live in Postgres and are editable directly from operator UI |
| sprint-21 | 2026-05-15 | E-05 | owner identity reset applied to admin UX and docs | first-party owner context should not be modeled as just another external person |

## Releases

| Version | Date | Contents | Tag |
|---|---|---|---|
| v0.1.0 | 2026-05-11 | infra stack on server | infra-v0.1.0 |
| v0.2.0 | 2026-05-11 | monorepo skeleton | docs-v0.2.0 |
| v0.3.0 | 2026-05-11 | core DB migration | db-v0.3.0 |
| v0.4.0 | 2026-05-11 | telegram ingestion | ingest-v0.4.0 |
| v0.5.0 | 2026-05-11 | extraction tables + entity runtime | extract-v0.5.0 |
| v0.6.0 | 2026-05-11 | persona runtime | persona-v0.6.0 |
| v0.7.0 | 2026-05-12 | task runtime + maintenance | ops-v0.7.0 |
| v0.8.0 | 2026-05-12 | summarization runtime | summary-v0.8.0 |
| v0.9.0 | 2026-05-13 | architecture reset docs | arch-v0.9.0 |
| v1.0.0 | 2026-05-13 | canonical AI runtime + analytics API/UI baseline | runtime-v1.0.0 |
| v1.0.1 | 2026-05-14 | cutover verification + server-side audit tooling | runtime-v1.0.1 |
| v1.0.2 | 2026-05-14 | baseline GitHub Actions CI workflow + canonical-runtime ruff gate | runtime-v1.0.2 |
| v1.0.3 | 2026-05-14 | deterministic seed/fixtures bundle | runtime-v1.0.3 |
| v1.0.4 | 2026-05-14 | canonical-runtime mypy gate + src-layout mypy_path baseline | runtime-v1.0.4 |
| v1.0.5 | 2026-05-14 | manual deploy workflow + remote rollout script + migration-runner | runtime-v1.0.5 |
| v1.0.6 | 2026-05-14 | admin UI baseline with multi-page control room in mcp-rest-api | runtime-v1.0.6 |
| v1.0.7 | 2026-05-14 | admin operator actions + detail drill-down pages | runtime-v1.0.7 |
| v1.0.8 | 2026-05-14 | admin detail-page stabilization + live server UX smoke | runtime-v1.0.8 |
| v1.0.9 | 2026-05-14 | admin flash UX + person block/unblock controls | runtime-v1.0.9 |
| v1.1.0 | 2026-05-14 | direct LAN publishing for admin surface + root redirect | runtime-v1.1.0 |
| v1.1.1 | 2026-05-14 | admin data recovery tooling + backfill runbook | runtime-v1.1.1 |
| v1.1.2 | 2026-05-15 | owner identity normalization + Russian-first AI output baseline | runtime-v1.1.2 |
| v1.1.3 | 2026-05-15 | manual person tags, owner comments, and people-list segmentation filter | runtime-v1.1.3 |
| v1.1.4 | 2026-05-15 | owner identity reset in admin UX + canonical docs alignment | runtime-v1.1.4 |

## Open questions

- build-images workflow and fuller release automation
- richer provider policy extraction into standalone library
- grounded synthesis in API responses
- profile switching / re-embedding workflows beyond initial alias bootstrap
- privacy / erase cascade hardening for analytics and vector projections
- stricter controlled vocabulary or relationship labels on top of free-form manual tags
- canonical `owner_profile` and `relationship_annotation` tables instead of transitional `person.is_owner`
