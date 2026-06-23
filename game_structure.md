Game structure changes:

- Ensure locker event has at least 50% chance to appear before and after game event
- Shower event 50% chance after locker event
- 25% of press conference type event before game
- 25% chance of manager event after practice
- Add more events with multiple team mates
  - During practice
  - During games?
  - Locker room
  - Shower
- Ensure player gender is reflected in team roster (professional sports are split on gender)
- Identify other directly chained events as above

Core loop

- At the end of an event
  - Check for direct followup as above
  - Otherwise check for scheduled/deferred event matching current location and time, with preconditions satisfied
  - Otherwise 50% at context appropriate event using state drift (phase 25)
  - Otherwise, player free to navigate
