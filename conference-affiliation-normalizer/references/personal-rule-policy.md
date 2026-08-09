# Personal Affiliation Rules

Read this file when applying or extending the reviewed rules in `personal-rules.json`.

## Evidence hierarchy

1. Preserve the publication's raw affiliation text.
2. Query the exact `institution_raw.csv` reference before accepting a new fuzzy/ROR candidate.
3. Prefer an exact reviewed alias or a paper-and-author scoped correction.
4. Accept a ROR link only when the reviewed rule includes that ROR ID or AffilGood returns compatible evidence.
5. Propagate country or ROR values only when all supporting records agree on one value.
6. Resolve exact reviewed rules, unique identities, non-institutional markers, and atomic composites
   deterministically. Retain unknown organizations explicitly; route a row to review only if this
   deterministic classification itself fails.

## Extracted deterministic rules

- Normalize reviewed spelling variants for NUDT, TUM, Michigan, Virginia, Zhejiang, NUS, and Mysten Labs.
- Normalize reviewed aliases for CISPA, Ant Group, Baidu, Quancheng Laboratory, QI-ANXIN, Shanghai Qi Zhi Institute, and Zhongguancun Laboratory.
- Use `Shanghai Qi Zhi Institute` and `Zhongguancun Laboratory` as the fixed English display names; treat `Shanghai Qizhi Institute`, `Shanghai Qu Zhi Institute`, and `Zhongguancun Lab` only as aliases.
- Reject the Guangzhou Laboratory ROR link for Zhongguancun Laboratory.
- Keep `BNRist Zhongguancun Lab` distinct from Zhongguancun Laboratory.
- Apply the two reviewed CCS French multi-institution corrections only when both `paper_id` and `author` match.

## Rules intentionally not automated

- Do not carry project-local `INST####` identifiers into unrelated datasets. They depend on one generated institution dictionary and can change after renumbering.
- Do not merge organizations merely because their normalized strings are similar.
- Do not accept a historical ROR alias unless the current ROR name retains distinctive evidence from the observed name.
- Do not use an acronym when multiple active ROR records share it unless country evidence leaves exactly one candidate.
- Do not let an LLM review overwrite deterministic evidence. Store LLM suggestions as review candidates.

## Adding a rule

Add only a stable, reviewed mapping to `personal-rules.json`. Give it a unique ID, retain the observed alias,
and include ROR/location values only when confirmed. Require explicit review before enabling a broad pattern.
