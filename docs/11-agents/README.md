# 11 — Agents

Документация **общая для всех трёх агентов** (Claude Code, Codex, Cursor) — этот раздел объясняет, как они сосуществуют, как переключаться между ними и какие правила применяются ко всем.

- [agent-architecture.md](agent-architecture.md) — как устроен каждый агент, capabilities матрица, точки входа.
- [when-to-use-which.md](when-to-use-which.md) — какого агента выбирать под тип задачи.
- [shared-conventions.md](shared-conventions.md) — 20 правил, общих для всех агентов.
- [handoff-protocol.md](handoff-protocol.md) — как передавать работу между сессиями и агентами.
- [session-transitions.md](session-transitions.md) — переключение посреди задачи.
- [prompt-library.md](prompt-library.md) — готовые промпт-шаблоны под типовые задачи.

Точки входа агентов в корне репо:
- [`../../CLAUDE.md`](../../CLAUDE.md)
- [`../../AGENTS.md`](../../AGENTS.md)
- [`../../.cursorrules`](../../.cursorrules)

Все три ссылаются на эти файлы.
