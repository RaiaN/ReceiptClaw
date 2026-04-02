# Tesco Flatmate Billing Agent MVP

## Summary
Build a chat-first OpenClaw workflow that turns each Tesco receipt into a structured order, asks flatmates to confirm ownership and splits, computes who owes whom, runs a second-pass QA check on the math, and then sends payment chases plus grocery-gap reminders.

For the hackathon, optimize for a strong end-to-end demo in about 2 hours:
- Use a clean `receipt ingestion -> item extraction -> chat triage -> ledger -> reminders` pipeline.
- Design receipt input as an adapter, but default to the fastest working path.
- Keep payment confirmation manual in chat.
- Make persistent chasing simple and deterministic.

## Implementation Changes

### 1. Core flow
Create these subsystems:
- `receipt_ingest`: accepts raw Tesco receipt content and creates an `Order`.
- `receipt_parser`: extracts merchant, order date, total, line items, discounts, delivery fee, and candidate split items.
- `chat_orchestrator`: posts the order into the flatmate chat, asks who owns what, and tracks replies until the order is resolved.
- `ledger`: stores per-order allocations, payer, balances, payment status, and reminder state.
- `qa_check`: re-runs the allocation math independently and blocks settlement if totals do not reconcile.
- `reminders`: sends unpaid-balance chases and "you haven't ordered groceries in a while" nudges.

### 2. Receipt ingestion strategy
Use an explicit `ReceiptSource` interface with two implementations:
- `manual_text_input`: paste or forward email body into the system. This is the default demo path.
- `email_inbox_adapter`: reserved for a real inbox or webhook path if setup is quick.

Decision:
- Spend at most 20 minutes trying to wire a dedicated receipt inbox into OpenClaw.
- If that is not working cleanly, switch to `manual_text_input` immediately and continue the demo.
- The rest of the system should not care which adapter was used.

### 3. Data model and public interfaces
Define these core types:
- `Household { id, name, members[] }`
- `Member { id, display_name, chat_user_id, default_split_group? }`
- `Order { id, source, merchant, ordered_at, payer_member_id, currency, subtotal, fees, discounts, total, status }`
- `OrderItem { id, order_id, raw_label, normalized_label, quantity, unit_price, line_total, allocation_status }`
- `Allocation { order_item_id, member_id, share_type, share_value }`
- `Settlement { order_id, debtor_member_id, creditor_member_id, amount, status, confirmed_at? }`

Behavioral contracts:
- Every `OrderItem.line_total` must be fully allocated before an order can settle.
- `sum(item allocations) + unallocated fees/discount handling = order total`.
- The payer is the creditor by default unless explicitly overridden.
- Payment confirmation is a chat action, not a bank integration.

Fee and discount policy for v1:
- Delivery fees and basket-level discounts are split evenly across all participating members in that order.
- Item-level discounts stay attached to the relevant item.
- If a household wants a different rule later, make this configurable after the hackathon.

### 4. Chat UX
Use "agent proposes, users confirm":
- On receipt arrival, the agent posts a concise summary: order date, payer, total, extracted line items.
- It proposes ownership per item from heuristics:
  - obvious singular ownership from prior history if available
  - obvious shared items from keywords like milk, eggs, bread, toilet roll, etc.
  - otherwise mark as unresolved
- It asks each flatmate to reply in a constrained format such as:
  - `mine: coke zero, chicken`
  - `split 2: milk, eggs`
  - `split 3: loo roll`
  - `paid`
- Once all items are allocated, it posts:
  - per-person total
  - who owes whom
  - due status
- After that, the QA agent independently recomputes the numbers and either:
  - approves and posts the final balances
  - flags a mismatch and asks the main agent to re-open the order

### 5. Reminder logic
Implement two deterministic reminder jobs:
- `payment_chaser`
  - send first reminder 24 hours after balances are posted if unsettled
  - send follow-up every 24 hours until chat confirmation
  - stop once all settlements for the order are marked paid
- `grocery_gap_reminder`
  - if no new `Order` has arrived in the last 5 days, post a group nudge
  - if users reply with `already ordered`, suppress for 48 hours

## Suggested Build Order
1. Stub the data model and persistence layer first.
2. Build manual receipt ingestion and a Tesco email parser with sample receipts.
3. Build the chat orchestration loop for unresolved items and payment confirmation.
4. Add ledger calculation and settlement generation.
5. Add QA re-check as a separate agent or function using the same structured order data.
6. Add reminder jobs last.

## Test Plan
Use 3 concrete end-to-end scenarios:
- Single-payer order with clear ownership:
  - 2 personal items each, 2 shared items, delivery fee, one discount
  - verify allocations reconcile exactly to Tesco total
- Messy order with ambiguous items:
  - parser leaves some items unresolved, users clarify in chat, final balances update correctly
- Multiple outstanding orders:
  - one paid, one unpaid, one partially allocated
  - verify reminder logic only chases the unpaid settled order and does not double-count balances

Hard guardrail:
- QA check must fail if computed settlements do not match the order total to the penny.

## Assumptions and Defaults
- OpenClaw can orchestrate a group chat agent and call custom app logic or tools.
- Hackathon success means a believable demo, not production-grade inbox sync.
- Manual receipt forwarding or pasting is acceptable if inbox or webhook setup threatens delivery.
- Currency is GBP and rounding is to 2 decimal places using deterministic safe rounding.
- Historical preference learning is optional for the demo; simple keyword heuristics are enough.
