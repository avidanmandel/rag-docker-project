# ScoutMatch Agent update plan (apply stage only)

- Target agent: `scoutmatch-recruitment-agent-user5-avidan`
- Preserve existing four football Action Groups unchanged.
- Add Action Groups: ScoutMatchShortlistActionsAvidan, ScoutMatchRecruitmentBriefActionsAvidan, ScoutMatchRecruitmentWorkflowActionsAvidan.
- Instruction addendum: see deploy script `AGENT_INSTRUCTION_NATIVE_ADDENDUM`.
- Confirmation: set `sessionAttributes.write_confirmed=true` before write tools.
