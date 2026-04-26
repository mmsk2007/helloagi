# COSPLAY (Co-Evolving LLM Decision and Skill Bank) — analysis for HelloAGI

**Core idea:** A decision agent retrieves and follows skills from a learnable bank; a separate pipeline segments rollouts, proposes contracts, and curates the bank (merge/split/retire).

**Key architecture:** Decision loop + skill bank agent + cold-start data; skills are structured contracts tied to trajectories.

**Useful for HelloAGI:** Skill contracts with lifecycle fields, retrieval scoring, extraction after successful `TriLoop` runs, promotion gated by SRG/MemoryGuard.

**Defer:** Full co-training loop, game-specific encoders, multi-agent bank competition.

**MVP implemented:** `SkillContract`, `SkillBank`, `SkillRetriever`, `SkillExtractor`, `SkillManager` facade, TriLoop extraction hook.

**SRG integration:** Treat promoted skills as memory-like artifacts; run `check_skill_promotion` before persistence.

**Risks:** Over-extraction produces noisy skills; mitigate with minimum steps, verifier summary, and conservative promotion.
