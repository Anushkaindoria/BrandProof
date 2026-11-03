# BrandProof evaluation results

Claim set: 62 labelled NovaTech claims (16 hard). Run on 2026-11-02.

### Rules-only

| Subset | Claims | Precision | Recall | False-positive rate | F1 | Category agreement | TP/FN/FP/TN |
|---|---|---|---|---|---|---|---|
| All | 62 | 100.0% | 61.9% | 0.0% | 76.5% | 100.0% | 26/16/0/20 |
| Easy (rules-style) | 46 | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 26/0/0/20 |
| Hard (paraphrase / out-of-rules) | 36 | n/a | 0.0% | 0.0% | n/a | n/a | 0/16/0/20 |

Rewrite check (rules-only rewrite engine): 26/26 flagged bad claims received a proposed fix (100.0%); 26/26 of those re-audit clean (100.0%). This is an automatic proxy, not human acceptance.

Flagged per label: correct 0/20, wrong_fact 12/16, unsupported_claim 8/14, exaggeration 6/12

Missed (16):
- c33 [wrong_fact, hard] "Lasts all day on seven thousand milliamp hours."
- c34 [wrong_fact, hard] "Battery: 7000 milliamp-hours."
- c35 [wrong_fact, hard] "Two year warranty included."
- c36 [wrong_fact, hard] "Fully covered for 24 months."
- c45 [unsupported_claim, hard] "Survives a dive in the pool without a scratch."
- c46 [unsupported_claim, hard] "Rated for underwater use."
- c47 [unsupported_claim, hard] "Clinically proven to improve your sleep."
- c48 [unsupported_claim, hard] "The most trusted phone brand in the country."
- c49 [unsupported_claim, hard] "Voted phone of the year by experts."
- c50 [unsupported_claim, hard] "Tested to survive a drop from ten metres."
- c57 [exaggeration, hard] "Unbeatable performance that crushes every rival."
- c58 [exaggeration, hard] "Mind-blowing speed like nothing else on earth."
- c59 [exaggeration, hard] "Insanely powerful and flawless in every way."
- c60 [exaggeration, hard] "You will never need another phone again."
- c61 [exaggeration, hard] "AMAZING!!! BUY NOW!!!"
- c62 [exaggeration, hard] "Absolutely incredible, life-changing performance."

_Gemini comparison not run: pass --gemini with LLM_API_KEY set to add it._
