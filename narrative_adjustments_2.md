# Narrative enhancement v2

The Narrative as presented still feels incoherent or jumpy. Here are some ideas to improve on that.

## Overview

- Presentation: Sequence of screens
  - May have choices / interaction
  - May be a single logical dialogue split due to word wrapping etc.
- Sequence of events
  - An event produces multiple screens, for setup, recap, choices, consequences
  - Events may dictate followup events, either direct continuations, or scheduled/deferred for the future
  - Event may be triggered
    - as direct followup to currently resolved event
    - as async continuation of a prior event, triggered by conditions being satisfied (relationship, stats, other event resolved (flag))
      - either randomly generated or belonging to an arc
    - as random spawn based on local context (location, time, role gallery etc.)
- Parallel ongoing arcs
  - Arcs spawn or schedule events connected to a narrative thread
  - An arc can be hard coded or generated ad hoc
  - The arc has an overall theme and distinct participants with given roles, that will show up in child events, to ensure consistency

- Phases
  - Narrative: event to event
  - Game: structured progression, custom visualization, chance to affect outcome by adjusting levers and making choices
  - Navigation: unstructured movement between scenes, could trigger narrative, game phases

## Presentation

Currently events always follow the same presentation format:

- Describe context
- Recap prior event/arc chain if relevant
- Narrate situation leading to player choice
- Present two choices
- Narrate application of player choice ("{player} goes for the ball and shoots hard!")
- Narrate consequences and outcome of the action

We should consider having three different "event templates" to vary this a bit, and perhaps include variations on player choices (more options, two choices per event)

## Arcs

Currently it can be hard to see when an arc comes into play, possibly because it doesn't show through event narration as desired. To improve this, and to make debugging easier we could do the following

- Select one hard coded arc origin event as the starting event
- Randomly generate two other background arcs that are likely to spawn events as play progresses
- Add a menu option to show arcs / "journal".
- Add a label to events (shown below time and date) indicating the arc name, when presenting an event belonging to an arc
- Ensure initial arcs are generated after the "main"/initial cast (see below).

## Cast

- Generate a few distinct roles that can be set up for recurring functions:
  - Ensure there is a dedicated "Best friend" generated on the same team as the player. Starts with high friendship, moderate intimacy.
  - Ensure there is a geek non-playing friend (relevant for analysis, research, education events). Starts with high friendship, low intimacy.
  - Ensure there is a rival on the same team. Starts with low friendship, moderate intimacy.
- Add an option to "inspect" the main cast members, showing name, role/team membership, relationships, known secrets:
  - Player character (show stats?)
  - Best friend
  - Geek friend
  - Team manager
  - Top 5 romantic interests based on current state

## Event reusability, coverage

- Locations could possibly be tagged with event type suitability (domain, nature).
- Event blueprints could specify event type ("residence, non-player", "locker room, player team"), or avoid locking it in if not needed, to allow domain/nature resolution.
- Event blueprints could contain variations driven by context (tone especially).

## Free form navigation

- When likelyhood of event spawning is less than 100%, there is a chance the player is left in a location with "nothing to do".
- Provide navigation options with labels. These should be deterministic according to the generated location graph. If the right arrow on the stadium takes you to the locker room, it should always do so. In the locker room, prefer left (or top-left or bottom-left) tacking you back to the stadium, while right could take you to the showers, down to the managers office, and so on.
- Advance time by increments when moving between locations (could be static 15 minute or dependant on assumed distance (locker room - shower is instantaneous, while Stadium-home is 30 minutes)).
- Check for pending/deferred arc events when leaving (which will interrupt navigation before time advances), and when arriving (after advancing time).
- Otherwise randomly spawn event based on context
- Ideal flow:
  - When continuing from an event, continue to event ~75% of the time (adjustable)
  - When navigating free form, spawn event ~25% of the time
  - This includes having pending arc events, so hard to tweak directly, but could have a "tension" lever that is reduced whenever an event is triggered, and increased whenever player navigation happens. This should increase probability of spawned context event, but not dictate it.
  - Goal is to get a feel of moving between narrative and downtime periods.

## Scheduled events

- Rather than player teleporting to stadium at game time, should present a deadline for showing up "Game vs {opposing team} today. Be at locker room by 14:30" or similar
- Phase changes and game starts when player reaches the designated location. Could use a similar mechanism for arc events "You have a date with {person}, meet at ${restaurant} by 20:00"
- Missing a game (or date) has consequences (as dicated by the game/event). This could be a reduction in team morale, relationships etc.
