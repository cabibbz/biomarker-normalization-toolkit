# Review Rubric

Every idea that survives the hard constraints gets scored from `0` to `5` in each category.

## Scoring Scale

- `0`: actively bad for this business
- `1`: weak
- `2`: below bar
- `3`: acceptable
- `4`: strong
- `5`: ideal

## Weighted Categories

| Category | Weight | What good looks like |
|---|---:|---|
| Compliance safety | 25 | avoids HIPAA ops, avoids DTC privacy exposure, avoids clinical interpretation |
| Speed to revenue | 20 | can be sold and delivered within 30 days |
| Buyer pain intensity | 20 | painful enough that teams already spend money or engineering time on it |
| Reusability / corpus growth | 15 | every project improves the mapping engine for the next customer |
| Delivery simplicity | 10 | customer-run, low support burden, few moving parts |
| Revenue quality | 10 | supports annual licenses, support, and update contracts |

Total possible score: `500` raw points before dividing by `5`.

## Pass Thresholds

- `85-100`: build now
- `70-84`: only build if it directly unlocks a signed customer
- `50-69`: backlog only
- `<50`: reject

## Review Questions

Answer these before scoring:

1. Who is the specific buyer?
2. What exact mess are they paying to remove?
3. Can we deliver without hosting live PHI?
4. What reusable mapping asset do we gain?
5. Can this become a license + update + support offering?
6. Does this pull us toward DTC, hosted PHI, or clinical workflow sprawl?

## Scoring Worksheet

Use this formula:

`weighted_score = ((compliance * 25) + (speed * 20) + (pain * 20) + (reuse * 15) + (delivery * 10) + (revenue * 10)) / 5`

## Decision Rule

Even if the weighted score is high, reject the idea if it breaks any hard constraint.

