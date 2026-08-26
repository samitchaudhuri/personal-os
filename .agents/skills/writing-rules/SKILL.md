---
name: writing-rules
description: Voice and style rules for the user's prose, edits, commit messages, slide copy, READMEs, vault notes, spec openings, and any written content. Use whenever producing or revising prose. Covers structure, precision, narrative over form-style labels, tone, and an end-of-pass checklist. For vault notes, spec openings, voice refinement, or long pieces, also read appendix.md.
---

# Writing rules

Based on analysis of writing samples (academic papers, technical notes, presentations, vault notes). Phrase banks, long templates, worked examples, and context-specific voice notes live in [appendix.md](appendix.md). Open it when refining voice, writing vault notes or spec openings, or working on long pieces.

## Guidelines

1. **Introduce concepts before terms** — Explain why an idea is needed, then name it; stay consistent after that. When near-synonyms exist (e.g. calmness, composure, stillness), pick the most precise and memorable one and use it exclusively — don't vary terms for stylistic reasons.

2. **Simple to complex** — Intuition or outcome first, then mechanics; keep direction consistent through the piece.

3. **Structure by intent** — For arguments: problem → solution → evidence. For procedures, specs, habits, or how-tos: reason or goal first, action second.

4. **Clear structure** — Sections answer one question each. Build each explanatory paragraph around one purpose and one memorable claim. Develop that claim in a logical sequence, with each sentence doing one job. Close by reinforcing the claim or, when helpful, leading into the next paragraph. Keep paragraphs short for reasoning, but not down to a single sentence — that fragments ideas into disconnected claims. Lists only for parallel items. When ideas are sequential or one enables another, make the relationship explicit — not just "three techniques" but name the dependency (A is the prerequisite for B).

5. **Precision and evidence** — Numbers, examples, comparisons; avoid "very fast," "highly scalable," "significantly better" without a yardstick.

6. **Clarity and economy** — Active voice when it clarifies responsibility; analogies only if they shorten understanding or make an abstract concept memorable and sticky; cut jargon that does no work; avoid em dashes (use commas or hyphens as grammar allows).

7. **Narrative, not forms** — No fake headers or bold+colon labels like `**Purpose:**`, `**How:**`, `**Key point:**` before fragments; say it in ordinary sentences unless you are literally filling a schema.

8. **Bold default off in prose** — Do not bold for structure, labels, or scanning. Use bold only when the user asks, or for a single rare emphasis the sentence cannot carry otherwise. Tables and checklists may keep light bold on row keys when that is already the note's convention.

9. **Full sentences over parenthetical dumps** — Put purpose, actors, and constraints in ordinary sentences. Do not pack side facts into long parenthetical lists or semicolon piles that only a rereader can unpack. Short citations in parentheses (`([[@cite]])`) and brief clarifiers are fine; if the parenthesis needs its own verb or list, promote it to a sentence. This applies to section headings too — fold a qualifier into the heading's wording (e.g. "Codex Desktop — Code, about 10 minutes") rather than tacking it on in parens; a heading is still something a reader has to parse, not just a label.

10. **Parallel bullets only** — Same kind of item (options, comparable facts, steps with no prose between). Otherwise use short paragraphs.

11. **Tone** — No clichéd "insights," corrective reframing, rhetorical stunts, or breathless hype. For personal notes, reflections, and exploratory writing: use "we" rather than "you" — it reads as collaborative discovery rather than instruction. Reserve "you" for genuinely prescriptive content.

12. **Affirmative first** — Lead with what to do, not what to avoid. Prefer "Clear thinkers prepare for the future, not predict it" over "Clear thinkers don't predict the future, they prepare for it." Negation-first sentences read as corrective reframing (see #11) and slow the reader. Keep a trailing negation only when the negated half is the cliché or default the reader would otherwise assume; drop it when the affirmative alone is specific enough that the contrast adds rhythm but no information.

13. **Section intros argue; filing notes do not open sections** — When the user asks where content should live (single home, DRY, embed, cross-links), put routing in a decision log, an embed caption, or the chat recommendation. Reader-facing section openings still explain why the reader needs the idea: situations, shared mechanism, constraint. Do not open with "Shared home for…", "Single source of truth for…", "This section is used by note A and note B", or a catalog of which runbook owns which steps. Architecture or planning mode does not suspend these rules for prose that will land in a note.

14. **Order terminology as a ladder** — When introducing a list of related terms (a glossary, a Terminology section), order them by their real containment or dependency relationships, not alphabetically or by definition convenience. Pick a climbing direction deliberately per chain: trunk-to-leaves (the concept the reader already has intuition for, then the mechanics underneath it) or leaves-to-trunk (small primitives building up to what they compose), whichever is the easier climb for that particular chain. Forward references are fine if the climb direction calls for them; avoiding them is not the goal.

## Writing checklist

- [ ] Numbers or concrete comparisons instead of vague praise?
- [ ] Problem → solution → evidence (or why → what for procedures)?
- [ ] No form-style label lines; bold default off in prose (rare emphasis only)?
- [ ] No long parenthetical dumps — qualifications live in full sentences?
- [ ] Terms introduced after the need for them is clear?
- [ ] No clichés, reframing tricks, or hype patterns from the appendix?
- [ ] Structure and headers clear; lists only when parallel?
- [ ] Each explanatory paragraph has one purpose and one memorable claim; each sentence does one job; the close reinforces the claim or bridges forward when helpful?
- [ ] Analogies (if any) shorten the path or make the concept stick?
- [ ] Single precise term chosen among near-synonyms and used consistently?
- [ ] Relationships between ideas made explicit, not just listed in parallel?
- [ ] "We" voice for personal/reflective notes; "you" only for prescriptive content?
- [ ] Sentences lead with the affirmative action; trailing negation kept only when it pre-empts a likely misreading?
- [ ] Section intro states why the reader needs this idea (not where the content is filed)?
- [ ] Vault notes and spec openings: examples in the sentence ("such as"), then-chains, one verb per action (see appendix vault-note example)?
- [ ] Terminology or glossary lists ordered as a deliberate ladder (trunk-to-leaves or leaves-to-trunk), not arbitrarily?

For expanded do/don't phrases, outline templates, good/bad examples, and per-genre voice, see [appendix.md](appendix.md).
