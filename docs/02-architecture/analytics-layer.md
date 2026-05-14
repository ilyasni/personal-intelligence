# Analytics Layer

Analytics в новой архитектуре PIL отделён от personal memory.

## Зачем отдельный слой

Memory-слой отвечает за:

- факты;
- задачи;
- interaction summaries;
- people/context memory.

Analytics-слой отвечает за:

- communication KPIs;
- response dynamics;
- initiative balance;
- friction / health signals;
- drill-down до evidence-backed окон.

Это разные задачи, поэтому analytics не смешивается с persona memory в одну сущность.

## Первая волна analytics

В первую волну входят:

- `GET /analytics/overview`
- `GET /analytics/conversations`
- basic HTML UI `/analytics`
- evidence-backed drill-down через `analysis_window`

## KPI catalog

Базовые сигналы первой волны:

- `responsiveness`
- `initiative_balance`
- `topic_drift`
- `conversation_health`
- `friction`
- `activity`

Часть из них считается полностью deterministic, часть — hybrid, но всё равно хранится с evidence.

## Источники данных

Analytics строится из:

- deterministic preprocessing features;
- `analysis_window.features`;
- `analytics_signal`;
- `task`;
- `interaction`;
- optional graph/vector enrichments для drill-down.

## Privacy boundaries

Analytics не должен:

- ставить личностные диагнозы;
- назначать клинико-психологические labels;
- выдавать “скрытые черты характера” как canonical output.

Допустимы только operational и communication-level выводы.

## Context7 rule

При реализации analytics-слоя обязательна Context7-сверка по используемым библиотекам и SDK:

- FastAPI
- Qdrant client
- Neo4j Python driver
- LangGraph / LangChain, если analytics flow затрагивает orchestration

Без этой сверки change не считается готовым к merge.
