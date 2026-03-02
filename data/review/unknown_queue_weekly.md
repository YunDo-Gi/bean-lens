# Unknown Queue Weekly Report

- Window: last 7 days
- Source: `postgres`
- Total events: 18
- Unique raw values: 6

## Domain Breakdown

domain | events | compound_raw_events
--- | --- | ---
process | 0 | 0
roast_level | 1 | 0
country | 0 | 0
variety | 1 | 0
flavor_note | 16 | 0

## Reasons

reason | count
--- | ---
no_dictionary_match | 18

## Top Unknown Values

### roast_level

count | raw
--- | ---
1 | 라이트 로스트

### variety

count | raw
--- | ---
1 | 수단 루메

### flavor_note

count | raw
--- | ---
7 | Kyoho Grape
7 | White Wine
1 | 애플망고
1 | 유칼립투스

## Typo Hints (Review Required)

domain | raw | count | suggested_term | score
--- | --- | --- | --- | ---
(none)

## Recommended Actions

- Split compound values at extraction/parsing stage when `compound_raw_events` grows.
- For `flavor_note`, keep strict mode and only add typo aliases after manual review.
- Promote high-frequency unknown terms to `terms.py` when they represent new canonical concepts.

