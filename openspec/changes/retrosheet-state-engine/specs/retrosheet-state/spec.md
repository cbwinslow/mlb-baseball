## Purpose

Defines the Chadwick-compatible layer of the Retrosheet Python package: reading event files, iterating game
state, and producing the output of the six Chadwick tools, proven equal to the real tools.

## ADDED Requirements

### Requirement: Output equals the Chadwick tools

For every event file in a validated season, `cwevent`, `cwgame`, `cwdaily`, `cwsub`, `cwcomment` and `cwbox`
(text, `-X`, `-S`) SHALL produce the same bytes as the real Chadwick tool built from the reference source, for
all fields (`cwevent -f 0-96 -x 0-66`) and all options, run on the same files. Equality SHALL be checked on whole
output; no field or option may be skipped silently.

#### Scenario: A validated season matches

- WHEN a season's files are run through the port and the real tool with the same options and team/roster files
- THEN stdout is identical and the report shows 0 differences

#### Scenario: Command-line behaviour matches

- WHEN an option is valid, malformed, conflicting or missing
- THEN stdout, stderr and exit status equal the real tool's (the usage text prints the bare tool name)

### Requirement: Rules come from the C source, not from output

Each ported module SHALL be a function-by-function translation of the matching Chadwick C source and SHALL carry
Chadwick's copyright and GPL notice. Behaviour SHALL NOT be added because it was seen in output.

#### Scenario: Reviewer checks provenance

- WHEN a ported module is reviewed
- THEN it names its C source file, keeps the notice, and every deviation is listed in its docstring

### Requirement: Where the C is undefined the port is explicit

Where the C crashes, exits, dereferences NULL or reads uninitialised memory, the port SHALL raise `ValueError` or
use a defined value, and SHALL document it. Test inputs on which the C has undefined behaviour SHALL be skipped
visibly, not compared. Plays Chadwick cannot parse SHALL be flagged by the new-season guard, not guessed.

#### Scenario: Unparseable play

- WHEN a play cannot be parsed
- THEN the port raises `ValueError` naming the game and play (or the guard reports it), as the C reports an error

### Requirement: The package stays independent

`retrosheetpy` SHALL import only the Python standard library and itself. It SHALL NOT import `mlb_baseball`, a
dataframe library, a database driver or native code, and SHALL NOT need Chadwick at run time (Chadwick is a
test-time reference only).

#### Scenario: Clean import

- WHEN the package is imported in a clean environment
- THEN none of `mlb_baseball`, pandas, psycopg or a Chadwick binary is loaded or needed
