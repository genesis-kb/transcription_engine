# BIP/BOLT Explainer Pipeline

This document proposes an initial pipeline for issue #7: LLM-based explainers for
BIPs and BOLTs. The goal is to connect canonical Bitcoin and Lightning
specifications with BitScribe transcript context, then generate explanations for
different audiences.

## Goals

- Sync BIPs from `bitcoin/bips` and BOLTs from `lightning/bolts`.
- Parse specification markdown into structured metadata and chunks.
- Detect BIP/BOLT references in existing transcripts.
- Use transcript context when available to improve explanations.
- Generate beginner, developer, and researcher explanations.
- Cache generated output by source version, audience, prompt version, and model.

## Pipeline

```text
BIP/BOLT GitHub repos
        |
        v
[Spec sync]
        |
        v
[Raw spec storage]
        |
        v
[Spec parser and chunker]
        |
        v
[Parsed specs, chunks, aliases]
        |
        +-----------------------------+
        |                             |
        v                             v
[Transcript reference matcher]   [Vector index]
        |                             |
        v                             v
[Transcript/spec links]       [Retrievable context]
        |                             |
        +-------------+---------------+
                      |
                      v
            [Explanation strategy]
                      |
        +-------------+--------------+
        |                            |
        v                            v
[Single-shot generation]       [RAG generation]
        |                            |
        +-------------+--------------+
                      |
                      v
              [Audience output]
                      |
                      v
          [Explanation cache and API]
```

## Components

### Spec Sync

Fetch markdown files from the upstream specification repositories and track the
source version used for every generated explanation.

Initial metadata to store:

- spec type: `bip` or `bolt`
- spec number
- title
- source repository
- source path
- source commit
- content hash
- raw markdown
- synced timestamp

### Spec Parser

Convert raw markdown into structured sections. The parser should prefer markdown
heading boundaries before falling back to character or token windows.

Useful BIP sections include:

- abstract
- motivation
- specification
- rationale
- backwards compatibility
- reference implementation
- test vectors

Useful BOLT sections include:

- overview
- message formats
- requirements
- feature bits
- protocol flow
- compatibility notes

### Transcript Reference Matcher

Detect when existing transcripts mention BIPs or BOLTs.

The first implementation can combine regex matching with a small curated alias
map.

Example regex patterns:

```text
\bBIP[-\s]?(\d{1,4})\b
\bBOLT[-\s]?(\d{1,3})\b
\bBLIP[-\s]?(\d{1,3})\b
```

Example aliases:

```text
Schnorr -> BIP-340
Taproot -> BIP-341
Tapscript -> BIP-342
PSBT -> BIP-174
HD wallets -> BIP-32
Lightning invoices -> BOLT-11
Offers -> BOLT-12
```

Each match should eventually include a confidence score and nearby transcript
context.

### Explanation Strategy

The explainer should choose between two generation paths.

Single-shot generation is used when only the spec text is available. The LLM
receives the parsed spec and produces a structured explanation for the requested
audience.

RAG generation is used when linked transcript context exists. The LLM receives
the relevant spec chunks plus retrieved transcript chunks. The spec remains the
source of truth, while transcripts provide explanatory and historical context.

## Audience Levels

### Beginner

Explain the motivation and core idea in plain language. Avoid unnecessary jargon
and include a glossary for unavoidable technical terms.

### Developer

Focus on implementation details, validation rules, data structures, edge cases,
compatibility concerns, and related specifications.

### Researcher

Focus on tradeoffs, assumptions, design alternatives, security considerations,
and historical context.

## Suggested Output Shape

Generated explanations should be stored as structured data so the frontend can
render each section independently.

```json
{
  "spec": "BIP-340",
  "title": "Schnorr Signatures for secp256k1",
  "audience": "developer",
  "summary": "...",
  "motivation": "...",
  "how_it_works": "...",
  "key_concepts": [
    {
      "term": "Schnorr signature",
      "definition": "..."
    }
  ],
  "technical_details": "...",
  "implications": "...",
  "related_specs": ["BIP-341", "BIP-342"],
  "linked_transcripts": [
    {
      "transcript_id": "...",
      "title": "...",
      "matched_text": "Taproot and Schnorr",
      "confidence": 0.92
    }
  ],
  "qa": [
    {
      "question": "Does this change old Bitcoin addresses?",
      "answer": "..."
    }
  ]
}
```

## MVP Scope

Start with a small set of high-value specs:

- BIP-32: hierarchical deterministic wallets
- BIP-174: partially signed Bitcoin transactions
- BIP-340: Schnorr signatures
- BIP-341: Taproot
- BIP-342: Tapscript
- BOLT-11: Lightning invoices
- BOLT-12: offers

## First Implementation Step

The smallest useful implementation can add:

- a spec sync service skeleton
- a parser interface
- a transcript reference matcher using regex and aliases
- an explainer service interface
- cached output schema

LLM generation and full vector search can be added after the data model and
matching flow are reviewed.

## Guiding Principle

The specification text is the source of truth. Transcript context should improve
understanding, but it should not be treated as normative protocol behavior.
