# Writing rules appendix

Canonical rules (short): [SKILL.md](SKILL.md). This file adds examples, phrase banks, and outlines so the main file stays small for token cost.

## Phrases to use

These banks are for academic and technical papers. Do not open a vault note or OS spec with them.

**Problems:** "A primary limitation is…", "Human experts exploit [technique], while automated approaches…", "This approach addresses the gap between…", "The challenge lies in…"

**Solutions:** "This technique ensures…", "The model captures…", "We achieve this by…", "The approach works as follows:"

**Evidence:** "Experimental results show…", "Table X demonstrates…", "As illustrated in Figure Y…", "The data indicates…"

**Structure:** "First, we define…", "Building on this foundation…", "This leads to…", "In summary…"

## Phrases to avoid

**Clichéd transitions:** "The key insight is…", "This is where it gets interesting…", "Here's where X shines…", "The real power comes from…"

**Corrective reframing:** "This isn't about X. It's about Y.", "You think this is X. It's actually Y.", "It's not X, it's Y."

**Negation-first openings:** "Don't predict the future, prepare for it" / "We don't optimize for X, we optimize for Y." Lead with the affirmative instead: "Prepare for the future, not predict it" / "We optimize for Y, not X." Keep a trailing negation only when the negated half is the cliché the reader would otherwise assume; drop it when the affirmative alone is specific enough.

**Rhetorical tricks:** "The difference?" [answer], "Those [things]? They're [explanation]", sentences opening with "This is where…" / "Here's where…"

**Breathless tone:** emoji stacks in formal writing, one-sentence paragraphs for drama, "mind-blowing" / "game-changing" / "revolutionary", fake suspense

**Empty intensifiers:** "critical insight", "comprehensive analysis", "significant impact", "robust solution" — replace with a measurable claim (e.g. "reduces latency by 30%")

**Punctuation:** em dashes — prefer commas or a simple hyphenated compound where grammar allows

**Form-style labels:** `**Purpose:**` / `**How:**` / `**Mechanism:**` as pseudo-fields; weave the same content into sentences and link out for theory

**Filing-cabinet section intros:** "Shared home for…", "Single source of truth for…", "This section is used by [[Note A]] and [[Note B]]. Job-specific setup stays on each runbook." Routing belongs in a decision log or embed caption. Open the section with why the reader needs the idea (situations, shared mechanism, constraint), not with where the file lives.

## Message structure patterns

Section-level skeletons only: real `##` / `###` headings, not permission to stack label lines in the body. Sub-bullets only when parallel.

### Technical explanations

Use this heading stack for papers and long technical explainers. Do not use it for vault notes or OS spec openings. Those use [Vault notes and spec openings](#vault-notes-and-spec-openings).

```markdown
## [Clear header: what this explains]

[1–2 sentence context / problem]

### Key components
- Component 1: brief definition
- Component 2: brief definition

### How it works
1. Step one with specifics
2. Step two building on step one

### Example
[Concrete example with numbers]

### Results / implications
[What this achieves, with evidence]
```

Headings carry the topic; do not repeat the same idea as an inline label before every paragraph.

### Notes / summaries

```markdown
## [Topic / session name]

### Key takeaways
- Main point 1 with context
- Main point 2 with context

### Technical details
- Implementation detail or constraint

### Practical application
- How to use this
- Example scenario
```

If a takeaway needs more than one sentence of motivation, use a paragraph under the heading instead of label-prefixed rows.

### Outreach / email

```markdown
Subject: [specific subject]

[Greeting]

[Core message: 2–3 sentences]

[Optional context: 1–2 sentences]

[Clear ask or next step]

[Sign off]
```

Keep under ~150 words; lead with the ask; specific and personal ("I" statements); avoid heavy bullets.

## Examples

### Good technical writing (paragraph)
> "The DPU processing substrate of 16K PEs resembles a Coarse Grained Reconfigurable Array (CGRA). Unlike CPUs, the instructions in the PEs are statically scheduled and not reordered at run time. The PEs are tightly coupled and proceed in lock step. This architecture spatially flows and reuses data from local memories to provide higher computation efficiency compared to temporal parallel architectures such as GPUs."

Why it works: specific numbers, defined term (CGRA), concrete comparisons, explains why, no filler jargon.

### Good technical writing (sentence level)
Precise without jargon bloat:
- "The DPU architecture overcomes the von Neumann bottleneck by spatially flowing and reusing data from local memories"
- "SAT-based formulation can explore a variety of memory access latencies during compilation"
- "Templates capture prerequisites as a set of choices"

Problem → solution at the sentence level:
- Problem: "Ensemble approaches neither guarantee optimal quality nor provide a measure of their blind spot around optimal solutions."
- Solution: "SAT-based compilation technique overcomes the limitations of prior ensemble approaches."

### Good note structure (parallel bullets)
> "### Context window management  
> - Critical limitation: models advertise 200K tokens but effective capacity much lower  
> - Context engineering more important than prompt engineering for production apps  
> - Performance degrades as context window fills beyond ~50% capacity  
> - Solutions include file organization, strategic context inclusion, conversation compaction"

Why it works: clear header, parallel bullets, numbers, actionable. Use prose paragraphs instead when each line needs its own "why."

### Bad writing
> "The key insight here is that the DPU architecture represents a paradigm shift. It's not about traditional computing - it's about reimagining how we handle data locality. This is where the architecture really shines. The comprehensive approach to spatial computation is truly revolutionary."

Why it fails: clichés, corrective reframing, vague claims, no numbers, buzzwords.

### Bad vs good section intro (filing vs why)

Bad (architecture voice leaked into the note):
> "Shared home for Google OAuth terms used by [[Obsidian Vault Sync and Backup Runbook]] and this note. Job-specific setup stays on each runbook."

Good (why the reader needs the section):
> "Personal OS reaches Google in more than one place, for example pulling inbound mail and calendar into the OS (this note), and syncing this Obsidian vault through Google Drive ([[Obsidian Vault Sync and Backup Runbook]]). Both use OAuth 2.0 authorization for Google APIs. This section names the shared OAuth pieces so both notes use the same words, even though we keep the two jobs in separate Cloud projects where a mistake in one cannot reach the other."

Why the good one works: concrete situations, shared mechanism, purpose of the section, constraint that makes shared vocabulary necessary. The DRY/embed decision stays in the decision log or chat.

## Voice in different contexts

- **Academic / technical papers:** P → S → E; numbered sections; formal but not stiff; figures and tables with real numbers.
- **Technical notes / documentation:** short paragraphs when reasoning matters; bullets only when parallel; clear headers; why a step exists, then what to do.
- **Outreach / email:** brief, ask first, personal, specific next step, minimal structure.
- **Blog / public:** open with a concrete observation or datum; no throat-clearing; evidence-backed claims; minimal emoji; no corrective reframing.

