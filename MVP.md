# First MVP: Cough and Sore Throat Chatbot

Status: learning prototype; clinical content and routing rules are drafts.

This document records our agreed direction and the build order for the first MVP. It contains requirements and exercises, not implementation code.

## 1. Purpose

Help a user describe symptoms through a multi-turn conversation, keep track of their answers, and produce a useful summary they can share with a clinician.

Here, **assessment** means checking reported symptoms and deciding what information or next step is needed. It does not mean confirming a disease.

The MVP must remain useful when it cannot suggest a possible cause. A model saying it is confident is not proof that its answer is correct.

## 2. Scope

| Item | First MVP |
|---|---|
| Symptoms | Cough, sore throat, or both |
| Patient age | 5 years or older |
| Person answering | Patient, or a caregiver answering for a young child |
| Language | English |
| Intended care-navigation region | Ho Chi Minh City, Vietnam |
| First interface | Local terminal |
| Development data | Fictional patients and conversations; a small, source-tracked medical reference collection for RAG |
| Main output | Symptom summary and downloadable Markdown conversation record |
| Initial model approach | Evaluate Qwen2.5-3B-Instruct Q4_K_M as a local candidate; no fine-tuning |

Age 5+ is a product boundary, not a clinically validated boundary. Child-specific questions and rules need separate review.

The terminal exercise is the first coding milestone, not the complete MVP. Natural-language handling and the remaining conversation behavior are added after the basic question-and-answer loop works.

Hospital matching, the filterable dashboard, and booking remain part of the product plan. They come after the assessment prototype and require verified facility data. See section 13.

## 3. Required conversation behavior

### Start a session

- Create a separate session for each conversation.
- Identify whether the user is the patient or a caregiver.
- Record the patient's age and whether they report cough, sore throat, or both.
- Reuse information already supplied rather than asking for it again.
- Give urgent disclosures priority over setup questions.
- Explain scope limits when the patient or symptoms are unsupported. Do not let that response suppress a reported emergency concern.

### Ask and understand questions

- Select questions from a prepared question bank.
- Ask one clear question at a time where practical.
- Select the next question based on missing information and the draft workflow.
- Interpret short answers using the question currently awaiting an answer.
- Extract relevant information volunteered anywhere in the conversation.
- Clarify unclear or conflicting answers without inventing missing facts.
- Allow the user to say they do not know or prefer not to answer.
- Avoid repeatedly asking questions already answered, declined, or recorded as unknown.
- Briefly redirect unrelated requests while still checking the message for relevant symptoms.

### Handle changes and urgent disclosures

- Keep the original conversation unchanged.
- Update the current summary when a user clearly corrects an answer.
- Keep separate facts for each symptom.
- Distinguish corrections from changes over time.
- Reconsider affected decisions after an answer changes.
- If the urgent-routing rule applies, stop ordinary questioning and enter an explicit urgent-handoff state.
- Preserve pending questions without automatically resuming them.
- Never delay the urgent message for report generation, question completion, or hospital comparisons.

The software can test these transitions using clearly marked fictional rules. Actual medical triggers and responses require clinical review. Uncertainty must not be treated as evidence that the situation is safe.

### Finish the conversation

- Summarize known facts, missing information, and unresolved contradictions.
- Present a possible cause only when supported by the reviewed workflow.
- Allow a valid finish without naming an illness.
- Give next-step advice only within the available reviewed content; otherwise state the prototype's limitation.
- Do not infer urgency solely from uncertainty or questionnaire completion.
- Do not produce prescriptions, invented disease probabilities, or lists of every disease for every possible missing answer.

## 4. Draft question bank

The existing 12-question draft is the starting point. Its detailed wording, clarification prompts, sources, and review status should be maintained separately as the question bank grows.

| ID | Information collected | Important storage rule |
|---|---|---|
| Q01 | Age | Unknown age does not become a guessed age |
| Q02 | Current breathing difficulty | Unknown does not mean normal breathing |
| Q03 | Ability to swallow saliva | Distinguish painful swallowing from inability to swallow |
| Q04 | Symptom onset and duration | Separate answer for each symptom; preserve approximate wording |
| Q05 | Symptom progression | Separate answer for each symptom and relevant time |
| Q06 | Measured temperature | Store reading, unit, and measurement time separately when known |
| Q07 | Runny nose | Keep distinct from a blocked nose |
| Q08 | Fluid intake | Record reduced intake or uncertainty explicitly |
| Q09 | Change in urination | Unknown does not establish normal hydration |
| Q10 | Ongoing medical conditions | Distinguish none, unknown, and declined |
| Q11 | Current medicines | Preserve an unnamed medicine as reported but unidentified |
| Q12 | Smoke or dust exposure | Do not infer exposure from job title or address |

Each definition needs its ID, information collected, wording, applicability, clarification behavior, source, and review status. Questions can be conditional; this is not a mandatory fixed sequence of 12 questions.

An answer may be partly complete. For example, a temperature reading without a unit should be preserved while the unit is clarified.

## 5. Data to store

These are logical records. They do not require a database in the first coding milestone.

| Record | Main fields |
|---|---|
| Question definition | ID, wording, information needed, applicable symptoms, draft rules, source and review status |
| Question asked | Definition ID, target symptom, exact wording, time asked, associated messages |
| Patient fact | Fact ID, information type, symptom if applicable, value, answer state, source message, reporter, time reported, time described if known |
| Session | Session ID, patient age, person answering, symptoms, facts, current question, ordered messages, session state, ending reason |

The same question definition can collect separate facts: Q04 for cough and Q04 for sore throat must not share one answer.

### Answer states

| State | Meaning |
|---|---|
| Unanswered | Information has not been supplied |
| Answered | A usable answer was supplied |
| Unclear | The answer needs clarification |
| Unknown | The user does not know |
| Declined | The user prefers not to answer |

Store question applicability separately. Store which question is awaiting an answer separately. A negative answer such as “no runny nose” is an answered fact, not an unanswered field.

### Session states

- In progress: ordinary questioning can continue.
- Urgent handoff: ordinary questioning has stopped.
- Completed: the summary is ready.
- Stopped: the user ended the conversation or the prototype could not continue; preserve the reason.

For corrections, retain the old fact as superseded and identify the current fact. For changes over time, retain both observations with their time context.

## 6. Application and model responsibilities

| Component | Responsibility |
|---|---|
| Conversation engine | Manage state, select questions, apply reviewed rules, decide permitted actions |
| Language model | Interpret free text, propose fact updates, phrase the selected question or supported summary |
| Retriever | Find relevant, reviewed reference passages with source information; return no sufficient evidence when appropriate |
| Validation | Check proposed updates, required fields, and permitted actions before accepting model output |
| Exporter | Build the Markdown report from stored messages and facts |
| Interface | Display questions, collect input, and show results |

The model should not freely invent the question bank, clinical rules, facility rankings, or missing answers. Correctly formatted output can still be wrong and needs evaluation.

Handle model timeouts and invalid responses without corrupting the session or treating a failed assessment as a negative finding. Do not include unvalidated medical output in the final report.

### Local model candidate: Qwen2.5-3B-Instruct Q4_K_M

Assumption: "qk4" means the Q4_K_M GGUF version. Record the exact file and revision before evaluating it; other 4-bit versions are different artifacts.

Qwen's model card lists 3.09 billion parameters, instruction-following and structured-output capabilities, a 32,768-token context limit for this model, and a Q4_K_M file of approximately 2.1 GB. Runtime memory is higher than file size because inference also needs working memory and conversation storage. A supported context length does not guarantee reliable use of every part of that context. [Official model card](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF)

Working recommendation: evaluate it for narrow jobs such as extracting symptom facts, recognizing corrections, and phrasing a selected question. This is an engineering starting point, not a claim that it has passed our task or is clinically reliable. Quantization stores weights at lower precision to reduce memory use and can change output quality.

- Use the Instruct model and its correct chat template.
- Keep each task small. Send the current question, relevant recent messages, structured facts, and only the needed reference passages.
- Keep question selection, urgent routing, and state updates under application control. A missed symptom extraction can still defeat a later rule, so evaluate the complete path from user message to action.
- Validate output structure and meaning. A JSON-shaped answer can still contain invented facts.
- Use a separate embedding model for semantic search; this chat model is not the embedding model selected for the RAG index.
- Compare the exact Q4 build against a higher-precision version or a stronger model on the same held-out conversations if important errors persist. Do not assume a larger model automatically establishes clinical safety.
- Measure fact accuracy, negation, caregiver/patient attribution, correction handling, urgent-message handling, unsupported claims, response time, and peak memory. Record hardware, runtime, model revision, quantization, prompt version, and settings.

The official 3B release uses the Qwen Research License, which grants research/evaluation use and requires a separate license for commercial use. Revisit model licensing before commercial hospital integration. [Official license](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE)

## 7. Markdown report

Include:

- Session identifier and report date.
- Available patient context and who answered.
- Current symptom summary, with each symptom kept separate.
- Unknown, declined, and unresolved information.
- Any supported assessment and next step, clearly separated from reported facts.
- Exact questions and answers in their original order.
- Whether the conversation finished, stopped early, or entered urgent handoff.
- Relevant content and workflow versions for tracing the result.

Generate the transcript directly from stored messages. Do not ask the model to recreate it from memory. Clearly label the learning-prototype status.

## 8. Privacy and basic reliability

- Use fictional data during development.
- Do not request names, exact addresses, or identifiers without a defined need.
- Keep API keys outside source files and version control.
- Start with session state in memory and explicit local report export. Database persistence can follow later.
- Do not write conversation contents into routine debug logs.
- Keep sessions separate; starting a new session must not reuse the previous patient's facts.
- Define retention and deletion behavior before introducing persistent patient data.
- Check the model provider's data handling before sending real health information.

## 9. Data collection and preparation for RAG

**RAG (retrieval-augmented generation)** means searching a reference collection and supplying relevant passages to the model when it answers. It does not train the model or guarantee that an answer is correct.

The goal is a small, traceable dataset that covers the supported workflow. "Complete" means the collection and processing pipeline meet the requirements below; it does not mean collecting all medical knowledge.

Keep three datasets separate:

| Dataset | Purpose |
|---|---|
| Medical reference collection | Source passages used for RAG explanations |
| Question bank and routing rules | Explicit, reviewed decisions about what to ask and when to stop or hand off |
| Evaluation conversations | Fictional cases and expected results used to test the application |

Do not add evaluation answers or patient conversations to the shared reference index. Later facility records should be a separate structured dataset so dashboard filters work on verified fields.

### 9.1 Choose sources and record coverage

Begin with the specific pages below. Expand only when a coverage check identifies a gap. Source inclusion is conditional on the relevant reuse terms and clinical review.

| Source | Initial pages or entry point | Intended use |
|---|---|---|
| NHS | [Cough](https://www.nhs.uk/symptoms/cough/), [sore throat](https://www.nhs.uk/symptoms/sore-throat/) | General symptom information and care-seeking guidance; UK service instructions need local handling |
| CDC | [Group A streptococcal pharyngitis](https://www.cdc.gov/group-a-strep/hcp/clinical-guidance/strep-throat.html) | Clinician-oriented reference; distinguish its audience from patient-facing guidance |
| MedlinePlus / NLM | [Cough](https://medlineplus.gov/cough.html), [sore throat](https://medlineplus.gov/sorethroat.html) | Topic summaries and terminology; use only eligible sections |
| Vietnam care context | [Government travel guidance: Vietnam health](https://www.gov.uk/foreign-travel-advice/vietnam/health) | A starting reference for local emergency contact information, not a clinical protocol |
| Later facility data | [HCMC Department of Health portal](https://thongtin.medinet.org.vn/) and official hospital service pages, such as [City Children's Hospital](https://bvndtp.org.vn/7106-2/) | Verify facility identity and published services; these links do not imply a clinical quality ranking |

Make a coverage table connecting each supported topic and question to its source sections. Include child-specific guidance, urgent concerns, duration, progression, hydration, relevant background, and uncertainty. Mark gaps explicitly; do not fill them with model guesses.

These initial pages are not a complete pediatric or adult clinical pathway. Additional content needs clinical review before enabling affected decisions.

### 9.2 Check access and reuse before scraping

Maintain a source register: exact URL, publisher, topic, intended audience, applicable age groups and country, reuse terms, allowed collection method, required attribution, refresh policy, and review status. Mark unresolved fields as unknown.

- Prefer an official API or export when available. MedlinePlus provides [XML downloads](https://medlineplus.gov/xml.html) containing health-topic summaries and metadata. Select the relevant English records; links in those records do not grant permission to copy their target pages.
- MedlinePlus permits reuse of its public-domain topic summaries with attribution, while licensed encyclopedia and drug content have different restrictions. Exclude the latter without suitable permission. [Content-use policy](https://medlineplus.gov/about/using/usingcontent/)
- NHS content has reuse conditions covering attribution, refresh dates, adaptations, and exclusions. Do not copy its medical-device software or assume generated paraphrases retain NHS clinical approval. Decide how unchanged excerpts and adapted explanations will be attributed before serving them. [NHS terms](https://www.nhs.uk/our-policies/terms-and-conditions/)
- CDC content has exceptions and conditions, including attribution, no implied endorsement, preservation of substantive meaning, and notice that the material is available free from CDC. Check page-specific restrictions and applicability outside the US. [CDC policy](https://www.cdc.gov/other/agencymaterials.html)
- Check each site's robots.txt and access terms. Robot access rules are not a content license. Use reasonable request rates and respect access restrictions.
- For local hospital pages, record permitted uses before collection. Collect public service information only, not patient records, user accounts, or testimonials as clinical evidence.

Deliverable: an approved URL list and a register of excluded or unresolved sources with reasons. This step plans collection; it does not claim permission has already been established for every source.

### 9.3 Collect and preserve original content

For allowed HTML pages, scrape only the approved URLs. Prefer ordinary page downloads and HTML parsing; use browser rendering only if necessary. Avoid an unrestricted crawl of whole websites.

- Save the original response or official export as an immutable source snapshot where retention is permitted.
- Record requested and final URL, collection time, source publication/review date if shown, HTTP status, content type, and a content hash for detecting changes.
- Use timeouts, bounded retries, caching, and a log of failures. Detect redirects, blocked responses, empty pages, and error pages instead of indexing them as medical information.
- Keep collection separate from answer generation. A patient message must not trigger an uncontrolled internet crawl.

Deliverable: raw snapshots plus a collection manifest explaining what was collected successfully and what failed.

### 9.4 Extract, clean, and review

1. Extract article text, title, headings, lists, and meaningful tables. Remove menus, banners, footers, scripts, and unrelated recommendations.
2. Normalize whitespace and encoding. Preserve negation, numbers, units, age limits, exceptions, warnings, and the relationship between a condition and its instruction.
3. Remove exact duplicates and identify near-duplicates, keeping a record of their sources. Do not merge conflicting recommendations into a new rule.
4. Tag audience, age applicability, geography, language, topic, source date, and review state. An unknown age range is not automatically suitable for every age.
5. Compare cleaned text against the original. For this small starter collection, inspect every document, especially warnings and tables.
6. Keep UK/US service instructions identifiable. Do not mechanically replace an overseas emergency number and treat the entire pathway as validated for Vietnam.
7. Have appropriate clinical content reviewed before it is eligible to support advice. Keep unreviewed data in a clearly separate development collection.

Use source wording as the reference text rather than replacing it with an unchecked model summary. Store translations or derived explanations separately, with their own review state and attribution requirements.

Deliverable: clean documents, processing reports, source links, and a list of unresolved clinical or extraction issues.

### 9.5 Split into useful passages and add metadata

A **chunk** is a passage stored as one search result. Split by headings and meaning before using a size limit. As an experiment, start around 200–400 tokens per chunk and adjust based on retrieval tests and the embedding model's input limit; this is not a medical standard.

Keep warnings with their triggering conditions and actions. Include enough heading context to identify the symptom and patient group. Preserve table headers and any relevant footnotes. Retrieve adjacent or parent text when a passage alone is incomplete.

| Chunk field | Purpose |
|---|---|
| Chunk ID and document ID | Trace the passage to its parent document |
| Text and heading path | Preserve the passage and its context |
| Source URL and location in snapshot | Allow verification against the original |
| Publisher, audience, age applicability, country, language | Support appropriate filtering |
| Topic tags | Support symptom-specific search |
| Source date and collection date | Distinguish content age from download age |
| Rights and attribution record | Carry required reuse information into outputs |
| Review state and version/hash | Prevent use of unreviewed or superseded content |

Deliverable: a portable chunk dataset, such as JSONL, with stable identifiers and metadata. Retain documents and chunks even when an index must be rebuilt.

### 9.6 Build and connect retrieval

- Establish a simple keyword-search baseline first.
- Choose and evaluate a separate embedding model. An embedding is a numeric representation used to find passages with similar meaning.
- Embed eligible chunks and store their vectors with chunk IDs. Record embedding model/version, input formatting, and index settings so the index can be rebuilt.
- Filter on applicable metadata, then compare keyword, vector, or combined search on the evaluation set.
- Form search queries from relevant session facts and the current information need. Avoid assuming a guessed disease is already confirmed.
- Supply a small number of useful passages to Qwen; experiment with 3–5 as a starting point. Leave room for instructions, session facts, and the answer.
- Return source IDs with the passages. Check that referenced IDs exist and that the passages support the claims; a valid link alone is not proof.
- Treat retrieved text as evidence, never as instructions that can change application behavior.
- If search finds no sufficient evidence, conflicting content, or unsuitable patient-group guidance, clarify or state the limitation. A similarity score is not a disease probability.

Urgent checks must run without waiting for retrieval. RAG does not replace the question bank or reviewed routing rules.

### 9.7 Evaluate, version, and refresh

Create a small development set and a separate held-out test set containing ordinary wording, typos, negation, caregiver reports, ambiguous swallowing descriptions, unrelated requests, and questions unsupported by the collection. Record expected supporting passages and cases where the system should decline to infer an answer.

Evaluate separately:

- **Collection quality:** important text retained, correct metadata, no duplicate/error pages, traceable sources.
- **Retrieval:** expected evidence appears among the returned passages; inappropriate age groups or locations are not used for advice.
- **Generation:** claims follow the evidence and patient facts; no invented symptoms, citations, or reassuring conclusions from missing data.
- **Conversation:** corrections and urgent disclosures still lead to the expected actions.

The reference documents belong in the index; held-out conversations, expected answers, and reviewer labels do not. Keep near-duplicate test cases out of prompt-tuning examples. Passing a small test set does not establish clinical safety.

Version the source register, snapshots, cleaner, chunks, embedding model, index, and evaluation results together. Refresh according to each source's terms and clinical review plan. Re-review changed content before activation; remove superseded chunks from active search and support rolling back a release. If required content is stale or withdrawn, disable affected advice rather than silently falling back to model memory.

### 9.8 What the completed RAG dataset contains

- Source register, coverage table, and documented exclusions.
- Permitted raw snapshots and collection manifest.
- Clean documents with provenance and processing versions.
- Reviewed chunks with complete required metadata or explicit unknowns.
- Rebuildable search index and embedding configuration.
- Separate development and held-out evaluation sets with results.
- Review records, attribution requirements, refresh rules, and known gaps.

Keep fictional patient cases separate from medical evidence. Do not label the dataset clinically complete merely because every page was scraped successfully.

## 10. Build order

| Milestone | What to build | Completion check |
|---|---|---|
| 1. Basic terminal exercise | Start session, choose cough/sore throat/both, ask onset separately, print summary | Both symptoms retain independent answers; a new session starts empty |
| 2. Question bank and state | Load definitions, track answers and current question, select applicable missing information | Unknown, declined, negative, and unanswered remain distinct |
| 3. Conversation changes | Clarifications, corrections, new developments, draft interruption states | Changes preserve history; urgent handoff stops the normal queue |
| 4. Markdown export | Export exact transcript plus current summary | Output matches stored messages and facts |
| 5. Source collection | Register sources and permissions; download exports or scrape approved pages | Traceable snapshots and a manifest; failures and coverage gaps recorded |
| 6. RAG data preparation | Clean, inspect, review, chunk, and index content | Evidence can be retrieved with correct context, metadata, and sources |
| 7. Model and RAG integration | Evaluate Qwen, interpret answers, validate updates, and generate supported explanations | Facts remain accurate; insufficient evidence produces a limitation, not a guess |
| 8. End-to-end evaluation | Run conversation and retrieval tests, including a held-out set | Expected facts and decisions are checked; limitations and model resource use documented |

Use Python for the initial terminal implementation. A web API, database, and browser interface can be added after the conversation engine works. Fine-tuning is not needed for this MVP.

Clinical review is a separate requirement before enabling real patient-facing advice; completing the software milestones does not satisfy it.

## 11. First test cases

The five fictional conversations already drafted are the starting cases. They test expected behavior, not exact generated wording or completeness of clinical assessment.

| Case | Required result |
|---|---|
| Clear answers | Record supplied facts, avoid unnecessary repetition, summarize accurately |
| Unclear answer | Clarify the specific missing meaning; keep uncertainty until resolved |
| Corrected answer | Update the correct symptom, preserve the old statement, reconsider affected decisions |
| Urgent disclosure | Enter urgent handoff immediately; do not continue questions or show comparisons |
| No supported likely cause | Respect declined information and produce a useful summary without inventing an illness |

Also check: answers given before a question, patient versus caregiver wording, two symptoms with different durations, partially answered questions, unsupported ages, unrelated text containing a health concern, model failure, and starting a second session.

## 12. Definition of done for the learning MVP

- [ ] One complete terminal conversation works from setup to export.
- [ ] The draft question bank is used consistently.
- [ ] Facts are tracked by information type and symptom, not question ID alone.
- [ ] Answer states remain distinct.
- [ ] Corrections and changes over time preserve their evidence.
- [ ] Urgent-handoff behavior can be tested and stops ordinary questioning.
- [ ] The model cannot directly bypass application state changes and validation.
- [ ] The application can finish without suggesting a disease.
- [ ] The Markdown report preserves the original conversation.
- [ ] The source register records permitted use, attribution, scope, dates, and review status.
- [ ] Collection, cleaning, and chunking preserve the source's meaning and provenance.
- [ ] The RAG index is reproducible and excludes test answers and patient conversations.
- [ ] Retrieval and answer grounding are evaluated separately, including missing evidence and wrong-population cases.
- [ ] Refresh and versioning rules prevent superseded or ineligible content from supporting advice.
- [ ] The exact Qwen candidate is evaluated on the target tasks; its limitations and license are recorded.
- [ ] The five agreed cases and basic failure cases have been checked.
- [ ] Clinical limitations and unreviewed rules are documented.
- [ ] Setup and run instructions are written.

Passing these checks establishes a software prototype, not clinical readiness.

## 13. Later product features to preserve

### Hospital and clinic dashboard

Build a filterable dashboard for Ho Chi Minh City with facility name, relevant services, age groups served, location, verified insurance information, hours or booking details, reason for matching, source, and last-checked date.

Match care needs even when no likely disease is identified. Mark unverified information explicitly. Evidence about disease-specific treatment quality may inform later comparisons, but the model must not invent “known for curing” rankings. Emergency messages take priority over browsing facilities.

### Appointment booking

Add hospital or clinic integration only after availability and booking outcomes can be verified. Require the user's explicit confirmation of the appointment and information being shared before submitting a booking.

### Broader scope

Add symptoms, languages, regions, or patient groups one at a time, with suitable content review and evaluation. Consider fine-tuning only after identifying a recurring measured problem and collecting appropriate reviewed examples.

## 14. Existing reference starting points

These sources were used in the draft discussion. They are not a complete protocol and do not validate this implementation. Recheck versions and local applicability during clinical review.

- [NHS: sore throat](https://www.nhs.uk/symptoms/sore-throat/)
- [NHS: cough](https://www.nhs.uk/symptoms/cough/)
- [CDC: clinical guidance for group A streptococcal pharyngitis](https://www.cdc.gov/group-a-strep/hcp/clinical-guidance/strep-throat.html)
- [UK government: Vietnam health and emergency contact information](https://www.gov.uk/foreign-travel-advice/vietnam/health)

## 15. How we will work

You write the implementation. Guidance should explain concepts, review your design, and offer hints using plain language. Exact code is provided only when you ask for it.

The immediate next step is milestone 1: build the small terminal exercise using the question, fact, and session records described above.
