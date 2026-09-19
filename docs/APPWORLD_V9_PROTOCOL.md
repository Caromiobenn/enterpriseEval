# Discovery guidance follow-up, separate from v8

V8's first 16 official test prefixes have been observed and are no longer eligible
as independent validation for this follow-up. At the first hourly check, its
completed runs had zero official successes and many unknown-tool/API errors.
This motivates a prompt-only discovery-guidance hypothesis, not a claim that a
prompt has already improved model ability.

Use the same two official train tasks for development. Choose all remaining 40 unique
test_normal prefixes by the original fixed SHA256 ordering, excluding *all*
variants of the 16 previously observed prefixes. Do not inspect their text or
solutions to select them. Preserve old v8 code, plans and results in their own
server directory.

Cross baseline/discovery_guidance prompts with the same Qwen2.5 AWQ models,
same three structured bridge tools, official grader, temperature 0.2, 40 model
calls and 1024 output tokens. Guidance explicitly explains the list/document/call
protocol, forbids guessing API names and identifiers, and asks the actor to
execute rather than merely explain. This is one prompt-bundle treatment, not
an isolation of each sentence. Realized token costs can differ despite equal caps.

40 tasks x 2 models x 2 prompts x 8 repeats = 1280 maximum planned episodes, ordered to
cover all tasks before later repeats. Randomize prompt order within each matched
model/task/repeat pair. Stop before the 09:00 cutoff; report missing cells.
Do not mutate frozen actor files after validation starts. Any further repair
must retain the failed version and move to a new version/evaluation boundary.

Compare prompts within matched model/task/repeat, average repeats inside task,
and disclose all truncation, protocol, context and official-grade failures.
This is a new prospective validation set for a hypothesis informed by v8,
not a retroactive improvement on v8's validation score. No extra benchmark
download, no public protected raw traces, no population significance claim.
