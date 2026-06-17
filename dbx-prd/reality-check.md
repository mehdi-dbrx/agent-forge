# BrickForge Reality Check

> Goal: Scan Databricks platform novelties, internal discussions, and product direction.
> Map what BrickForge does against what Databricks is building natively.
> Identify: what's still unique, what's now redundant, what needs to pivot.

> Status: IN PROGRESS

## Questions to answer

1. **What has Databricks shipped or announced since BrickForge started that overlaps?**
   - Agent Framework / Omnigent (already identified)
   - Agent Bricks updates
   - Genie API changes
   - Apps platform changes
   - Unity Catalog agent tools
   - MCP support natively
   - Any new "agent builder" UI

2. **What internal projects are in flight that BrickForge should be aware of?**
   - Omnigent (agent-framework repo) -- active, heavy development
   - Any other agent authoring tools
   - Any visual agent builder (no-code/low-code)
   - Databricks Apps improvements (auth, deploy, UI)

3. **What BrickForge features are now natively available on the platform?**
   - UC function auto-discovery as tools
   - Genie MCP
   - KA provisioning
   - Agent deployment
   - Chat UI

4. **What BrickForge features remain unique?**
   - AI data generation from domain description
   - Visual setup DAG (18 blocks)
   - One-click provisioning of full stack
   - .forge bundle export/import
   - GitHub export with start_local.sh
   - Self-healing SQL generation
   - Project management (multi-project, multi-workspace)

5. **Where should BrickForge position itself?**
   - Complement to Omnigent (setup + data layer)?
   - Standalone accelerator for SAs/demos?
   - Internal tooling only?
   - Open source community tool?

## Sources to scan

- [ ] Databricks internal Slack channels (agent-related)
- [ ] Omnigent repo (databricks-eng/agent-framework) -- done
- [ ] OmniAgents design doc -- done
- [ ] Recent Databricks blog posts / announcements
- [ ] Data+AI Summit 2025/2026 announcements
- [ ] Unity Catalog roadmap
- [ ] Apps platform roadmap
- [ ] Agent Bricks / Agent SDK updates
