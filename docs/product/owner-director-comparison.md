# Owner/Director Comparison

Use this table when explaining the upgrade to a founder, clinic director,
funeral-home director, school director, or local business operator.

| Workflow layer | Current owner-led work | Current AI CMO behavior | Upgraded owner/director behavior | Evidence path | Benefit |
|----------------|------------------------|-------------------------|----------------------------------|---------------|----------------|
| Intake | Owner repeats background in chat or meetings. | Agent asks for enough context to start. | Reusable intake captures goal, buyer, offer, constraints, assets, and approval owner. | `docs/system/user-pipeline.md` | Faster start with less repeated context. |
| Clarification | Owner discovers missing details after drafts arrive. | Agent may guess if the request is vague. | Neurosis-style gate asks one question at a time before execution. | `integrations/birkin/neurosis.md` | Fewer generic outputs and fewer restarts. |
| Work routing | Owner decides who should do the work. | Claude routing map chooses a playbook. | Triage maps every request to a workflow and role SOP. | `CLAUDE.md`, `playbooks/08-role-sops/` | Clear owner for every artifact. |
| Execution | Freelancers or staff follow inconsistent habits. | Existing playbooks produce useful drafts. | Role SOPs define inputs, steps, evidence, and failure modes. | `docs/system/role-sop-standard.md` | Repeatable work quality. |
| Complex projects | Owner manages several moving pieces manually. | Chain playbooks help but may lack acceptance gates. | Odyssey-style plan breaks work into verified phases. | `integrations/birkin/odyssey.md` | Complex work can be resumed and audited. |
| Creative assets | Copy and visuals are requested separately. | Text output may mention visuals without producing them. | codex-image-gen handoff requires prompt, approval, `visual_asset_status`, and PNG path when generated. | `integrations/birkin/codex-image-gen.md` | No fake image completion. |
| Review | Owner notices issues late. | Reviewer checks final artifacts. | Reviewer result becomes a required delivery field. | `prompts/shared/gate-check.md` | Trust surface before client delivery. |
| Learning | Lessons stay in chat history. | KB notes exist but can be inconsistent. | Reporter plus Morpheus-style maintenance queues durable improvements. | `integrations/birkin/morpheus.md` | The system gets easier to run over time. |
