# f1_hot_lap

## Artifacts

### Databases
1) Tracks - 1 Excel sheet tracking all track versions
      ID
      Track Name
      Track Version Number
      Track Version Start Date
      Track Version End Date
      Path to FBX file

2) Car Models w/ Livery - 1 Sheet that tracks all cars of each year versioned by their livery
  - ID
  - Season Year
  - Team Name
  - Driver Name
  - Car Number
  - Livery Version ID
  - Start Date
  - End Date

3) Calendar of all F1 Events
  - ID
  - Round Number
  - Circuit ID
  - Event Name (Practice 1, Quali, Etc)
  - Start Time
  - End Time

### Scripts
1 Master Script with the following steps

1) Create Blender Plugin - A Python Script that creates the Blender Plugin. This plugin showcases a GUI inside Blender and allows the user to provide input for
  - Year
  - Grand Prix
  - Session
  - Lap
  - Upto 3 drivers

2) Get Data From FastF1 - Take data from user input and then pull data from fast f1 given
  - A year
  - A round number
  - A session name (Q,R,SQ,SR)
  - A Lap (Best, or specific Lap Number)

3) Format and polish FastF1 Data to produce F1_HOT_LAP data - Takes the data from FastF1 and get's it in the format we need for the animation
  - Output Schema

4) Validate F1_HOT_LAP data - Produces a report of whether we are correct and have high confidence in the data



