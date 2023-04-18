Before:
- feature compiler
  - for each UFO:
    - makes a feature file from UFO's feature.fea
    - calls each feature writer which grows the contents of the feature file
    - compiles the feature file to OT stuff and puts into TTF


After:
- feature compiler
  - for each UFO:
    - asks each feature writer to prepare data (not necessarily feature code) for each UFO. Feature writers can look at existing feature file from the UFO but cannot change it yet
- runs each feature writer's preMerge step
  - for each UFO:
    - calls each feature writer which grows the contents of the feature file 
    - compiles the feature file to OT stuff