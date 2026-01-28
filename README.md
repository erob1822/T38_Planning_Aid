# T38PlanAid_EvansVersion
Parallel version of the T38 planaid with specific changes made to increase efficency/modularity. Goal is to create a working script, but not to replace the main version, more to find edits to suggest. Fully functional as of 1/27/2026.

Decreases the number of scripts to just 3. Data_Acquisition handles all API downloading, scraping, sorting, and CSV generation for all required data. KML_Generator generates a KML file, a masterdict.xlsx, and a plain text file with each airport, its classificiation, and any associated notes from wb_list.xlsx. T38_Planaid_E.py is the master script and includes a cfg object containing all API source data and airport requirements for modularity--easy to switch the script over to new requirements.

To create an exportable .exe, just run "build_exe.py" and you should come out with a folder containing both the .exe and the .xlsx it needs to run. Just zip and send.
