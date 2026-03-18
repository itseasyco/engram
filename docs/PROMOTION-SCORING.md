# Promotion Scoring

## Overview

The promotion scorer evaluates LCM session summaries to determine which facts should be promoted to LACP persistent memory. It scores across four dimensions:

## Scoring Formula

```
Score = (confidence × 0.4) + (strategic_impact × 0.3) + (reusability × 0.2) + (team_value × 0.1)
```

Each dimension scores 0-100, producing a weighted total of 0-100.

## Dimensions

### Confidence (40% weight)
How well-sourced and certain is this fact?

- **Trusted sources** (+20): code, git, documentation, API, test
- **Citations** (+10-20): 1+ citations = +10, 3+ = +20
- **Specifics** (+5 each): code blocks, file paths, version numbers
- **Hedging** (-5 each): "maybe", "might", "possibly", "unclear"

### Strategic Impact (30% weight)
Does it affect multiple projects or decisions?

- **Strategic keywords** (+8 each, max +50): architecture, migration, settlement, security, etc.
- **Multi-project** (+15): references to multiple easy-* projects
- **Decision language** (+10): "decided", "chose", "adopted"

### Reusability (20% weight)
Can other agents leverage this?

- **Reusability keywords** (+7 each, max +50): pattern, standard, template, shared, etc.
- **Code examples** (+8-15): 1 block = +8, 2+ = +15

### Team Value (10% weight)
Would other team members benefit?

- **Team references** (+15): names, roles, "team"
- **Documentation value** (+15): "how to", "setup", "configure"
- **Cross-project** (+10): references to easy-* projects

## Threshold

Default promotion threshold: **70**. Summaries scoring >= 70 are flagged for promotion.

## Categories

Facts are auto-categorized into:
- `architectural-decision`
- `operational-knowledge`
- `domain-insight`
- `integration-pattern`
- `debugging-insight`
- `team-context`
- `process-improvement`

## Usage

```python
from promotion_scorer import score_summary

result = score_summary({
    "content": "We decided to use Finix for payment processing.",
    "source": "code",
    "citations": ["architecture.md"],
    "project": "easy-api",
    "summary_id": "sum_abc123",
})

print(result["score"])       # 82.5
print(result["promote"])     # True
print(result["category"])    # "architectural-decision"
print(result["facts"])       # ["We decided to use Finix for payment processing."]
print(result["receipt_hash"])# "a1b2c3d4..."
```

## CLI

```bash
# Auto-promote with scorer
openclaw-lacp-promote auto --summary sum_abc123 --project easy-api

# Manual override (score = 100)
openclaw-lacp-promote manual --summary sum_abc123 \
  --fact "Finix is the payment processor" \
  --reasoning "Core architecture decision"
```
