---
oid: 01KGEJFSYNNCMZ2JD8VFRF2AF0
layer: ARCH
primary_unit: A.PLANNER
tags: [S.ADR]
status: active
---

# 报表优先数据平台（YME MVP）架构

目标：30 店连锁餐饮，接口全开放，先做报表，保证 **可回溯、可重算、可对账**。

## 分层

### Raw（原始层）

表：`raw_events`

- 只做“落地 + 审计”，不做业务计算
- 核心字段：`source_system/entity/store_id/external_id/event_time/ingested_at/payload(jsonb)/payload_hash/run_id`
- 幂等：唯一约束 `uq_raw_events_idempotency(source_system, entity, store_id, external_id, payload_hash)`
- 可重放：保留完整 payload + run_id + ingestion_runs 记录拉取范围

表：`ingestion_runs`

- 记录每次采集：开始/结束、状态、游标、数量、错误摘要

### Staging（标准化层）

表：`stores/products/categories/channels/orders/order_items/payments`

- 将 raw JSON 解析为结构化字段
- 时区统一为 `Asia/Shanghai`
- 去重策略：按 staging 表唯一键 upsert，使用 `updated_at`（若新数据更“新”才覆盖）

### Mart（指标预聚合层）

表：

- `m_sales_daily_store`
- `m_sales_daily_store_channel`
- `m_sales_daily_store_category`
- `m_sales_daily_store_sku`

策略：对日期范围 **delete + rebuild**，保证可重复执行（同数据跑两次，结果一致）。

指标（MVP）：

- `net_sales, gross_sales, discount, refunds, orders_cnt, items_cnt, avg_ticket`
- 成本相关字段预留：`cogs/gross_profit/gross_margin`（缺数据可为 NULL）

### Reconciliation（对账层）

表：`r_sales_daily_store_source`

- 维度：`store_id + business_date + source_system`
- 指标：订单数、净销售、折扣、退款、支付实收（来自 payments 汇总）

## 任务与重跑

任务（Celery）：

- `ingest_mock`：Mock Connector -> raw_events
- `transform_all`：raw->staging + staging->mart + reconciliation

重跑：

- 可按 `store_id`、日期范围（目前 staging->mart 支持 date_from/date_to）重复执行

## API

- `GET /api/health`
- `GET /api/stores`
- `GET /api/metrics/sales/daily?date_from=&date_to=&store_ids=&group_by=store|channel|category|sku`

返回结构固定：`{kpis, series, table_rows}`，前端不拼 SQL。

