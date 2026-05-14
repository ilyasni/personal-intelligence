# Evidence / Confidence Model

Этот документ фиксирует обязательный формат AI-выводов в PIL после архитектурного reset.

## Цель

Любой AI-вывод должен быть:

- проверяемым;
- привязанным к конкретным сообщениям;
- достаточно осторожным, чтобы не превращаться в “психодиагностику по переписке”;
- пригодным для deterministic projection в Postgres / Neo4j / Qdrant.

## Обязательная схема

Для каждого claim, task и analytics signal используется один и тот же базовый принцип:

- `claim` / `summary`: краткая формулировка вывода;
- `confidence`: число `0.0 .. 1.0`;
- `evidence_message_ids`: список `tg_message_id`, на которых основан вывод;
- `caveats`: список оговорок;
- `source_window_id`: идентификатор окна анализа.

В текущем runtime это материализуется через:

- `StructuredClaim`
- `StructuredTask`
- `AnalyticsSignal`
- `StructuredAnalysisResult`

см. [events.py](/D:/Workspace/personal-intelligence/libs/contracts/src/pil_contracts/events.py)

## Значение confidence

`confidence` в PIL не означает “математическую вероятность истины”.
Это operational score, который показывает, насколько вывод grounded в сообщениях текущего окна и насколько он устойчив после deterministic validation.

Рекомендуемая интерпретация:

- `0.00 - 0.39` — слабый сигнал, использовать только как hint.
- `0.40 - 0.69` — рабочий, но осторожный вывод.
- `0.70 - 0.89` — сильный evidence-backed вывод.
- `0.90 - 1.00` — почти полностью deterministic или явно выраженный в сообщениях вывод.

## Правила evidence

1. Если у claim/task нет `evidence_message_ids`, он не попадает в canonical projection.
2. `evidence_message_ids` должны ссылаться только на сообщения из текущего окна.
3. Если evidence слабое, система добавляет `caveats`, а не повышает confidence.
4. Нельзя подменять evidence общими словами вроде “по тону видно” без ссылок на сообщения.

## Caveat taxonomy

Рекомендуемые типы caveats:

- `heuristic extraction`
- `insufficient context`
- `single-message evidence`
- `cross-message inference`
- `language ambiguity`
- `time ambiguity`

## Non-goals

По умолчанию запрещены:

- personality labels;
- psychiatric / clinical labels;
- скрытые мотивы и “настоящие намерения” собеседника;
- непроверяемые интерпретации “характера”.

Допустимы только:

- факты;
- контактные данные;
- темы;
- задачи;
- communication signals;
- relationship hints, если они evidence-backed и сформулированы осторожно.
