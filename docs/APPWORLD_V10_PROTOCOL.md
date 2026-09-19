# Native versus constrained JSON protocol follow-up

At the 03:38 hourly check, v9 had 596 completed runs and no successes under either
prompt. Unknown top-level tool names, guessed APIs and truncation remain candidate
failure mechanisms. Keep all v8/v9 results and frozen code unchanged.

New experiment: hold discovery guidance, public API bridge, official grading,
model weights, temperature, model-call/output caps and context policy fixed;
compare native tool calling against a local-vLLM `guided_json` action protocol.
The JSON schema permits only the three bridge tool names, at most two calls per
response, and named argument objects. JSON observations are ordinary user messages;
native observations use tool messages. The JSON schema/instructions/serialization
are a **protocol bundle**, not an isolated decoder-only intervention. Native's
two-call limit remains a prompt request, whereas JSON enforces it in the grammar.

Develop on the same two official train tasks. Select 24 unique test_challenge
prefixes by the fixed SHA256 order without reading tasks or outcomes. Official
split metadata has 417 IDs and 139 prefixes, zero prefix overlap with test_normal;
therefore v8/v9 observed normal tasks are not reused for independent validation.
Validate disjointness explicitly before starting. Budget up to 24 tasks x 2 models
x 2 protocols x 8 repeats = 768 cells, coverage before repetition, until 09:00.
Report missing cells at cutoff, not fabricated completed counts.

Model outputs remain structured tool data, never host Python. Guided decoding
does not ensure valid API names, correct arguments, good planning or task success.
Training reference controls are separate: both official references pass live and
after close; replay through the structured bridge passes the 5-call reference,
while the 145-call reference hits the frozen 100-execution cap. This cap remains
unchanged and must be disclosed when interpreting low external scores.

Primary outcome: official success, with protocol errors/truncation/tool validity
as diagnostics. Pair protocols within identical task/model/repeat. Do not compare
challenge absolute rates to normal as if task difficulty were controlled. Keep
protected reference code, tasks and raw traces private.
