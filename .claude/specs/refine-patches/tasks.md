# Tasks: refine-patches

- [x] 1. chore(itinerary): claim Lane C on the package README status line
- [x] 2. feat(itinerary): flat response schemas for questions and patches, and the pure mapping from the flat shape to ItineraryPatch, with unit tests for the mapping
- [x] 3. feat(itinerary): questions() over complete_json, capped in code, skipping what the brief already answers, with its two recorded tests
- [x] 4. feat(itinerary): refine() returning validated patches, with the apply-on-a-copy filter, the signal-id strip and the patch cap, tests watched red first
- [ ] 5. feat(itinerary): model failure degrades to no patches instead of ending the run, with the test watched red first
- [ ] 6. feat(itinerary): replace_failed() one patch per failed stop, no reused or skipped place, with its three tests
- [ ] 7. feat(itinerary): wire build_planner with draft delegating to FakePlanner, say so in the README table, fixture and REAL_PLANNER run green
