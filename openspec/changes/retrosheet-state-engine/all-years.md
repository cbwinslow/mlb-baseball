# All-years proof: real Chadwick 0.10.0 vs port, byte for byte (run 2026-10-02)

> **Reference version.** "Chadwick 0.10.0" in this change means the Chadwick *development* source at commit `c685ab5` (`v0.10.0-26-gc685ab5`, 2026-03-13), which still reports version "0.10.0"; the installed `cw*` binaries and the source the port was translated from are that build. The released v0.10.0 tag differs (checked 2026-10-02: `cwevent`, `cwgame`, `cwdaily`, `cwsub` output differs on 2025 files; `cwcomment` is identical), so the port does not match the released 0.10.0.

Driver: packages/retrosheetpy/tests/reference/all_years.py. 1910-2025, every event file, with the season's real team/roster files. 2719 files, 0 diffs, 0 skipped files. 1964DET.EVA makes the C hit a documented intra-struct touches[-1] write (see chadwick_tool.TOUCHES_UNDERFLOW); it is compared, not skipped. 1964 cwbox was re-run alone after adding that tolerance; the other 695 runs are from the first full run.

| year | cwevent | cwgame | cwbox | cwdaily | cwsub | cwcomment |
|---|---|---|---|---|---|---|
| 1910 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1911 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1912 | 16 files, 32 checks, 0 diffs | 16 files, 32 checks, 0 diffs | 16 files, 48 checks, 0 diffs | 16 files, 32 checks, 0 diffs | 16 files, 32 checks, 0 diffs | 16 files, 32 checks, 0 diffs |
| 1913 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1914 | 27 files, 54 checks, 0 diffs | 27 files, 54 checks, 0 diffs | 27 files, 81 checks, 0 diffs | 27 files, 54 checks, 0 diffs | 27 files, 54 checks, 0 diffs | 27 files, 54 checks, 0 diffs |
| 1915 | 27 files, 54 checks, 0 diffs | 27 files, 54 checks, 0 diffs | 27 files, 81 checks, 0 diffs | 27 files, 54 checks, 0 diffs | 27 files, 54 checks, 0 diffs | 27 files, 54 checks, 0 diffs |
| 1916 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1917 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1918 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1919 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1920 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1921 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1922 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1923 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1924 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1925 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1926 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1927 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1928 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1929 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1930 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1931 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1932 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1933 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1934 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1935 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1936 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1937 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1938 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1939 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1940 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1941 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1942 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1943 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1944 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1945 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1946 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1947 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1948 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1949 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1950 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1951 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1952 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1953 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1954 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1955 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1956 | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 54 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs | 18 files, 36 checks, 0 diffs |
| 1957 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1958 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1959 | 17 files, 34 checks, 0 diffs | 17 files, 34 checks, 0 diffs | 17 files, 51 checks, 0 diffs | 17 files, 34 checks, 0 diffs | 17 files, 34 checks, 0 diffs | 17 files, 34 checks, 0 diffs |
| 1960 | 16 files, 32 checks, 0 diffs | 16 files, 32 checks, 0 diffs | 16 files, 48 checks, 0 diffs | 16 files, 32 checks, 0 diffs | 16 files, 32 checks, 0 diffs | 16 files, 32 checks, 0 diffs |
| 1961 | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 57 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs | 19 files, 38 checks, 0 diffs |
| 1962 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1963 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1964 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1965 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1966 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1967 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1968 | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 63 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs | 21 files, 42 checks, 0 diffs |
| 1969 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1970 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1971 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1972 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1973 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1974 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1975 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1976 | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 72 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs | 24 files, 48 checks, 0 diffs |
| 1977 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1978 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1979 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1980 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1981 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1982 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1983 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1984 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1985 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1986 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1987 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1988 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1989 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1990 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1991 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1992 | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 78 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs | 26 files, 52 checks, 0 diffs |
| 1993 | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 84 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs |
| 1994 | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 84 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs |
| 1995 | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 84 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs |
| 1996 | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 84 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs |
| 1997 | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 84 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs | 28 files, 56 checks, 0 diffs |
| 1998 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 1999 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2000 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2001 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2002 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2003 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2004 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2005 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2006 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2007 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2008 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2009 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2010 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2011 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2012 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2013 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2014 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2015 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2016 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2017 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2018 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2019 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2020 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2021 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2022 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2023 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2024 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| 2025 | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 90 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs | 30 files, 60 checks, 0 diffs |
| **checks** | 5438 | 5438 | 8157 | 5438 | 5438 | 5438 |

## End-to-end, installed commands (cli_all_years.py, 2026-10-02)

Built wheel installed in a clean virtualenv; real Chadwick 0.10.0 program vs the port's console script, both started by bare name with only their own bin directory on PATH, in a directory holding the season's event, team and roster files. 116 seasons (1910-2025) x 16 option sets (cwevent x4, cwgame x3, cwdaily x2, cwsub x2, cwcomment x2, cwbox default/-q/-X): 1856 comparisons of stdout, stderr and exit status, 0 differences, 21.7 GB of real-tool output compared. One comparison has empty output on both sides (2020, `-s 0601 -e 0630`: the 2020 season started in July). `cwbox -X` compared without the `pb` attribute (uninitialised memory in the C); `cwbox -S` not run (the real program segfaults).
Known deviation: the C prints argv[0] as typed in usage text; a Python console script always sees its full path, so the port prints the bare command name.
