# Data Rules

## Table of Contents

- [Overview](#overview)
- [1. Data Classification](#1-data-classification)
- [2. Data Flow Rules](#2-data-flow-rules)
- [3. PII Handling](#3-pii-handling)
- [Implementation Notes](#implementation-notes)

## Overview

These rules govern how agents classify, access, transform, and log data.

## 1. Data Classification

Classify all data (inputs, intermediate artifacts, outputs) before reading/writing.

- **Public**: safe to read/write broadly.
- **Internal**: accessible only to internal roles; do not publish externally.
- **Confidential**: located under `secrets/**` or otherwise marked confidential; **no role may access**.

## 2. Data Flow Rules

- Data may flow only from **higher sensitivity to lower sensitivity** when explicitly sanitized.
- Prohibited flows:
  - Internal → Public without sanitization
  - Confidential → any other classification
- When generating derived artifacts (reports, evidence), ensure they do not embed restricted content.

## 3. PII Handling

- Logs must not contain PII.
- If reporting requires referencing a user identifier, redact or tokenize it.
- If a document needs an example, use synthetic data.

## Implementation Notes

- Prefer allowlists over denylists for file path access.
- Apply redaction before writing any audit/evidence outputs.
- Store only the minimum necessary data to reproduce the decision (hashes, counts, metadata).
