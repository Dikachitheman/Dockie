# Problem Modeling Ideas

These notes capture the product-modeling direction behind Dockie: who the real users are, what they are actually anxious about, and which agentic workflows matter most on the US-West Africa ro-ro corridor.

## Who Actually Uses This Product

### The importer / freight forwarder

They often have 5 to 20 active shipments at once, each representing meaningful inventory value. Their real question is not just "where is it?" but "will this arrive before my customer's deadline, and how early will I know if that is changing?" They are not maritime specialists. They need exception alerts more than dashboards.

### The operations coordinator

They coordinate the chain end to end across port agents, customs brokers, trucking companies, and storage. Their core problem is timing. They need to book downstream logistics a few days ahead of arrival, and a wrong ETA creates costly rebooking churn.

### The analyst / manager

They look across shipments and carrier relationships over time. They care about retrospective performance: which carrier is more reliable on this lane, which vessels are consistently late, and where uncertainty keeps repeating.

## Agentic Product Ideas

### 1. Standby agents

The core pattern is simple: the user writes a natural-language condition plus an action, the agent checks on a schedule, and the action fires when the condition becomes true.

Example conditions:

- "When GREAT ABIDJAN is within 200 nautical miles of Lagos, send me an email."
- "If ship-002's ETA shifts by more than 24 hours in either direction, alert me."
- "When any of my shipments shows a freshness warning for more than 6 hours, notify me."
- "When ship-001 changes navigation status to at anchor, let me know."

This matches how operators actually think. They want to describe what matters once, then stop manually refreshing.

### 2. ETA impact assistant

When an ETA changes, the real user question is "what does this break?" rather than "what is the new date?"

The agent should reason about consequences:

- customs appointments that may need rescheduling
- trucking or warehouse bookings now at risk
- who should be warned
- which follow-up communications can be drafted automatically

### 3. Vessel intelligence briefing

Users evaluating a shipment or carrier want an on-demand summary of that vessel's recent behavior on the lane:

- average transit time
- on-time rate
- common anchorage or berthing pattern
- what caused delays on recent voyages

This is valuable because it synthesizes voyage history rather than just retrieving a single shipment record.

### 4. Multi-shipment comparison with agent narrative

Real operators are not managing one shipment in isolation. They want to know which active shipment is riskier this week and why.

The agent can compare:

- freshness of tracking data
- ETA confidence
- vessel or carrier track record on the lane
- ranked operational risk across active shipments

### 5. Port congestion context injection

On this corridor, arrival at anchorage is not the same thing as berthing. The more useful question is often "when will discharge actually become possible?"

The agent can use historical anchorage-to-berth patterns to produce a more realistic berth timeline beside the carrier-declared ETA.

### 6. Document drafting from shipment state

Operations teams repeatedly write the same kinds of updates:

- customer status emails
- customs pre-arrival notifications
- internal weekly shipment summaries

The agent can draft these directly from live shipment data and route them into email or document tooling.

### 7. Anomaly explanation mode

AIS and voyage anomalies are hard for non-specialists to interpret. When a vessel stops unexpectedly, changes course, or anchors in an unusual place, the agent should explain what that likely means in plain language and what typical next steps look like.

### 8. Proactive morning briefing

A daily briefing agent can summarize which shipments are normal, which need attention, and which operational actions are likely due soon. This turns the product from something the user checks into something that actively guides their day.

## Corridor-Specific Operational Ideas

These ideas are grounded in the operational reality of US to West Africa vehicle shipping, especially Lagos-area congestion, pre-clearance risk, and demurrage exposure.

### 1. Demurrage clock and pre-clearance readiness agent

Once ETA confidence is high enough, the agent works backward from likely berth date and helps the user track whether the documents and steps needed to clear before free days expire are actually ready.

This is especially valuable because the financial pain here is immediate and familiar: if paperwork starts too late, demurrage can stack quickly.

### 2. Vessel swap detection and impact agent

Carrier rotations can substitute one vessel for another. If the primary candidate vessel stops behaving like the booked sailing and another candidate starts matching the schedule, the agent can surface a likely substitution hypothesis, explain the implications, and draft the status inquiry the user would otherwise send manually.

### 3. Port congestion window agent

This helps answer the practical question of whether the user should already be pre-clearing, preparing for a rush-clearance scenario, or rethinking downstream timing because anchor-to-berth delay is likely to eat into their free days.

### 4. Carrier performance accountability agent

Over time, the system can build a private performance record across the user's own shipments:

- average delay versus declared ETA
- which vessels underperform on this lane
- whether a carrier's schedule tends to be systematically optimistic

This becomes decision support for future bookings, not just tracking for current ones.

### 5. Financial exposure calculator and alert agent

Users often do not see the cost of delay clearly until the invoice arrives. The agent can estimate exposure in real time by combining berth delay, free days, per-vehicle demurrage assumptions, and paperwork risk, then monitor thresholds like "alert me if projected exposure exceeds NGN 2 million."

## Why These Ideas Matter

All of these ideas push the product beyond simple location lookup. They treat shipment tracking as the starting point for operational reasoning:

- what changed
- what it means
- what action is likely needed
- what cost risk is emerging
- what should be watched automatically

That is the product frame Dockie is built around.
