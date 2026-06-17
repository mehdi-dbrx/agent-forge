eval_dataset = [
    # Original 3 questions
    {"inputs": {"query": "What compensation is a passenger entitled to for a 4-hour delay on a flight from Paris to New York?"}},
    {"inputs": {"query": "Can an airline refuse compensation by claiming extraordinary circumstances?"}},
    {"inputs": {"query": "What are a passenger's rights if they are denied boarding against their will?"}},

    # Edge-case questions (round 1)
    {"inputs": {"query": "My 2000km flight was delayed 2.5 hours. Am I entitled to meals at the airport? And am I entitled to financial compensation?"}},
    {"inputs": {"query": "If an airline offers me an alternative flight after cancellation and I arrive only 1 hour later than originally planned, do I still get full compensation or is it reduced?"}},
    {"inputs": {"query": "I booked a single ticket for London to Paris to New York. My Paris connection was missed due to a delay on the first leg. Which distance is used to calculate my compensation — London to Paris, or London to New York?"}},
    {"inputs": {"query": "My holiday package was cancelled because the hotel closed, but the flight itself still operated. Am I entitled to financial compensation under air passenger rights rules?"}},
    {"inputs": {"query": "The airline informed me of a cancellation 10 days in advance and offered an alternative flight departing 3 hours earlier than my original flight. Am I entitled to compensation?"}},
    {"inputs": {"query": "I volunteered to give up my seat in exchange for a travel voucher. I later found out that passengers who were involuntarily denied boarding received cash compensation. Was I treated fairly under the rules?"}},
    {"inputs": {"query": "The airline that actually flew me was different from the airline I booked my ticket with. Which airline is legally responsible for paying my compensation?"}},

    # Hard edge-case questions (round 2)
    {"inputs": {"query": "My flight was cancelled due to a pilot strike at the airline. The airline says extraordinary circumstances mean I'm not entitled to anything at all. Am I still entitled to meals and a hotel while I wait for the next available flight?"}},
    {"inputs": {"query": "My flight route covers 8,000km in actual flying distance but the straight-line distance between my departure and destination airports is only 5,000km. Which distance figure is used to determine which compensation bracket I fall into?"}},
    {"inputs": {"query": "I arrived at the check-in desk 40 minutes before my flight's scheduled departure. No specific check-in deadline had ever been communicated to me. The airline refused to board me and now claims I am not entitled to compensation because I checked in too late. Are they right?"}},
]
