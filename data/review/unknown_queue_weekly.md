# Unknown Queue Weekly Report

- Window: last 7 days
- Source: `postgres`
- Total events: 21
- Unique raw values: 15

## Domain Breakdown

domain | events | compound_raw_events
--- | --- | ---
process | 2 | 0
roast_level | 2 | 0
country | 0 | 0
variety | 4 | 0
flavor_note | 13 | 2

## Reasons

reason | count
--- | ---
no_dictionary_match | 21

## Top Unknown Values

### process

count | raw
--- | ---
1 | Washed(infused)
1 | 수세식(인퓨즈드가공) Washed(infused)

### roast_level

count | raw
--- | ---
2 | Midium-Light Roast

### variety

count | raw
--- | ---
3 | Castillo
1 | #1 Gesha

### flavor_note

count | raw
--- | ---
2 | Red-grape
2 | Welch's
2 | Lavender
1 | 적포도
1 | 웰치스
1 | 라벤더
1 | 적포도, 웰치스, 라벤더
1 | Red-grape, Welch's, Lavender
1 | Kyoho Grape
1 | White Wine

## Typo Hints (Review Required)

domain | raw | count | suggested_term | score
--- | --- | --- | --- | ---
(none)

## Recommended Actions

- Split compound values at extraction/parsing stage when `compound_raw_events` grows.
- For `flavor_note`, keep strict mode and only add typo aliases after manual review.
- Promote high-frequency unknown terms to `terms.py` when they represent new canonical concepts.

