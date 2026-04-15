# GHL Lifecycle Implementation Plan

## Context

- The canonical GHL pipeline and stage IDs already live in `backend/.env`.
- VCH should keep its richer internal state machine, but GHL must remain the operational CRM shell for contacts, opportunities, conversations, tasks, and workflow automation.
- Because the current GHL pipeline is coarser than the PRD lifecycle, exact VCH state must also be mirrored into GHL contact custom fields for clean two-way sync.

## Pipeline Mapping

Current outbound VCH to GHL stage mapping uses the existing `.env` stage IDs:

| PRD / VCH state | Current GHL stage env key | Notes |
|---|---|---|
| `LEAD`, `PRE_QUALIFYING` | `GHL_DEALS_STAGE_NEW_DEAL_SUBMITTED` | Keep welcome + qualification workflows here |
| `QUALIFIED`, `ENGAGED`, `PROFILED`, `MATCHING` | `GHL_DEALS_STAGE_CONDITIONAL_APPROVAL` | This is still a compressed bucket and should rely on custom fields for exact sub-state |
| `VEHICLE_SELECTED` | `GHL_DEALS_STAGE_FINAL_APPROVAL` | Good place for funding follow-up workflows |
| `FUNDING` | `GHL_DEALS_STAGE_DOCUMENTS_READY` | Credit app, docs chase, lender routing |
| `ACQUISITION_PENDING`, `ACQUIRED` | `GHL_DEALS_STAGE_ORIGINAL_DOCS_QC_REVIEW` | Current best fit, but these should eventually split into their own stages |
| `IN_TRANSIT`, `DELIVERED`, `CLOSED_WON` | `GHL_DEALS_STAGE_DEAL_FUNDED` | Delivery and post-sale automation can still branch off custom fields |
| `DISQUALIFIED`, `CLOSED_LOST`, `RETURN_PENDING` | `GHL_DEALS_STAGE_DECLINED` | `RETURN_PENDING` is operationally different and should get its own stage later |
| `EXCEPTION` | `GHL_DEALS_STAGE_NEW_DEAL_SUBMITTED` | Temporary fallback; should become its own exception stage/task queue |

## Required GHL Contact Custom Fields

These should be created in GHL and then added to `.env` as IDs:

| Purpose | Env key | Direction |
|---|---|---|
| Persist VCH user linkage | `GHL_CONTACT_CF_VCH_USER_ID` | VCH -> GHL, webhook resolution |
| Persist VCH deal linkage | `GHL_CONTACT_CF_VCH_DEAL_ID` | VCH -> GHL, webhook resolution |
| Exact VCH lifecycle state | `GHL_CONTACT_CF_VCH_DEAL_STAGE` | Bi-directional |
| Exact VCH funding state | `GHL_CONTACT_CF_VCH_FUNDING_STATE` | Bi-directional |
| Selected VIN | `GHL_CONTACT_CF_VCH_SELECTED_VIN` | Bi-directional |
| Buyer profile tier | `GHL_CONTACT_CF_VCH_PROFILE_TIER` | VCH -> GHL |
| Buyer profile completion percentage | `GHL_CONTACT_CF_VCH_PROFILE_COMPLETION_PCT` | VCH -> GHL |
| Pre-approval flag | `GHL_CONTACT_CF_VCH_PREAPPROVED` | Bi-directional |
| Pre-approval amount | `GHL_CONTACT_CF_VCH_PREAPPROVAL_AMOUNT` | Bi-directional |
| Pre-approval expiration | `GHL_CONTACT_CF_VCH_PREAPPROVAL_UNTIL` | Bi-directional |

Recommended next additions once ops wants richer automation:

| Purpose | Suggested env key |
|---|---|
| Last condition-report requested timestamp | `GHL_CONTACT_CF_VCH_CR_LAST_REQUESTED_AT` |
| Last condition-report completed timestamp | `GHL_CONTACT_CF_VCH_CR_LAST_COMPLETED_AT` |
| Last condition-report URL | `GHL_CONTACT_CF_VCH_CR_LAST_URL` |
| RouteOne application ID | `GHL_CONTACT_CF_ROUTEONE_APP_ID` |
| Current lender / source | `GHL_CONTACT_CF_VCH_LENDER_NAME` |

## VCH Action -> GHL Action Matrix

| VCH action / event | VCH source | GHL action now | Recommended workflow trigger |
|---|---|---|---|
| Buyer registration | `/v1/auth/register` | Create contact; persist `user.ghl_contact_id` | Welcome sequence |
| Quick match / full profile completion | `/v1/me/profile*` | Sync contact custom fields with exact VCH state and completion pct | Profile completion nudge / matching-ready |
| Recommendation selected | `/v1/me/recommendations/{vin}/select` | Update opportunity stage + selected VIN custom field | Funding follow-up |
| Start acquisition | `/v1/me/garage/{identifier}/acquire` | Add GHL note, sync selected VIN/state | Acquisition outreach / sourcing kickoff |
| Credit app submitted | `/v1/funding/{deal_id}/submit-app` | Sync exact funding state and stage | RouteOne follow-up / document chase |
| Pre-approved | admin today, RouteOne later | Sync user preapproval + funding state | Terms presentation / human follow-up |
| Funding confirmed | `/v1/funding/{deal_id}/confirm` | Stage update + funding state sync | Acquisition / document QC |
| Condition report requested | `/v1/me/vehicles/{identifier}/condition-report-request` | Add timeline note in GHL | Optional buyer reassurance SMS |
| Condition report completed | OVE detail push completion | Add timeline note + buyer notification | “Report ready” workflow |
| Carrier booked / in transit | logistics routes | Opportunity update + shipment note/task | Delivery countdown |
| Delivered | logistics/admin | Opportunity update | Review request / referral enrollment |
| Return initiated | return flow | Opportunity update + task + note | Return instructions / pickup coordination |

## RouteOne Guidance

### Recommended integration order

1. Keep `FundingCase` as the internal transactional record.
2. Add a RouteOne adapter layer behind the existing `/v1/funding/*` routes rather than coupling RouteOne directly to frontend flows.
3. Store the RouteOne application ID on `FundingCase` and mirror a summary into GHL custom fields.
4. Treat RouteOne as a lender/application execution service, not the CRM source of truth.
5. Use GHL for the buyer-facing workflow state, reminders, conversation history, and human tasking.

### Suggested state contract

| RouteOne / funding event | VCH funding state | VCH lifecycle state | GHL automation use |
|---|---|---|---|
| App created | `CREDIT_APP_SUBMITTED` | `FUNDING` | Start “application received” workflow |
| Pre-qualified / soft approval | `PRE_APPROVED` | `QUALIFIED` or `FUNDING` depending on UX | Notify buyer, request missing docs |
| Terms accepted | `TERMS_ACCEPTED` | `FUNDING` | Trigger documents-ready workflow |
| Final approval pending stips | `FINAL_APPROVAL_PENDING` | `FUNDING` | Missing-doc chase + HITL if stale |
| Fully funded | `FULLY_FUNDED` | `ACQUISITION_PENDING` | Kick sourcing/acquisition |
| Declined / failed | `FUNDING_FAILED` | `CLOSED_LOST` or `EXCEPTION` | Recovery / secondary lender / HITL |

### Implementation notes

- Prefer webhook-first from RouteOne if available; otherwise poll and reconcile on a schedule.
- Every RouteOne state change should do three things atomically in VCH:
  - update `FundingCase`
  - update `Deal.funding_state` and, when appropriate, `Deal.stage`
  - sync GHL custom fields / opportunity stage / timeline note
- Keep lender-specific documents and conditions in `FundingCase.conditions[]`; use GHL only for workflow-driving summaries.

## AI Agent / Orchestration Recommendation

Recommended architecture:

1. `GHL MCP` remains a tool server, not the orchestrator.
2. Use a durable orchestrator for long-running agent workflows and HITL pauses.
3. Use a memory layer for cross-agent recall, summaries, and handoff context.

Recommended stack direction:

- Best overall fit for production orchestration: Temporal-style durable workflows
- Best add-on for cross-agent memory/handoff: Memorix or MindState
- Best current “central brain” pattern for VCH: orchestrator service + memory service + MCP tool layer

Practical recommendation for VCH:

- Use a durable workflow engine for `QualificationAgent`, `FundingAgent`, `SourcingAgent`, `CommunicationAgent`, and `ReturnAgent`.
- Use GHL MCP as a shared CRM/action adapter across those agents.
- Use a separate memory layer for decisions, stalled-deal context, outreach history summaries, and handoffs.

Suggested split:

| Layer | Recommended role |
|---|---|
| Orchestrator | Durable state machine, retries, SLA timers, HITL checkpoints |
| Memory layer | Cross-agent memory, summaries, decision logs, retrieval |
| GHL MCP | Contacts, opportunities, conversations, tasks, workflows |
| VCH MCPs | Inventory, matching, funding, sourcing, returns, audit |

My recommendation today:

- If you want the safest production path, use a durable workflow engine first and add Memorix or MindState as memory.
- If you want the fastest experimentation path, start with LangGraph plus GHL MCP, but expect to add stronger durability around timers, retries, and long-running waits.

## Immediate Next Steps

1. Create the contact custom fields above in GHL and place their IDs in `.env`.
2. Decide whether `RETURN_PENDING` and `EXCEPTION` get dedicated GHL stages now or stay compressed for MVP.
3. Add a RouteOne adapter module and a `routeone_application_id` field on `FundingCase`.
4. Build workflow definitions in GHL for:
   - welcome
   - profile completion
   - funding follow-up
   - CR ready
   - acquisition start
   - missing docs / stalled funding
   - return initiated
5. Add a reconciliation job that reads recent GHL opportunity/contact changes and repairs missed webhook events.
