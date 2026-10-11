-- core.play_retro: every Chadwick cwevent field for Retrosheet plays, typed (ADR-305; openspec change widen-core-pitch-play).
-- One row per Retrosheet core.play row (keyed to core.play.id + season), partitioned by season like core.play.
-- No foreign key to core.play: conform rebuilds both tables together, and a FK from a partitioned table
-- would pin core.play's partitions as logged (the test harness runs them UNLOGGED). Orphans are checked by
-- conform's health check instead.
-- Not carried: load metadata (_season, _group, _scope, _loaded_at) and run1_auto_fl/run2_auto_fl/run3_auto_fl
-- (NULL in 100% of 16.7M rows on 2026-10-10). *_fl flags are boolean (T/F); integer-only columns are integer;
-- ids and codes stay text. Not registered for export (core.play/core.pitch stay local_research).

CREATE TABLE core.play_retro (
    play_id bigint NOT NULL,
    season integer NOT NULL,
    retro_game_id text,
    away_team_id text,
    inn_ct integer,
    bat_home_id integer,
    outs_ct integer,
    balls_ct integer,
    strikes_ct integer,
    pitch_seq_tx text,
    away_score_ct integer,
    home_score_ct integer,
    bat_id text,
    bat_hand_cd text,
    resp_bat_id text,
    resp_bat_hand_cd text,
    pit_id text,
    pit_hand_cd text,
    resp_pit_id text,
    resp_pit_hand_cd text,
    pos2_fld_id text,
    pos3_fld_id text,
    pos4_fld_id text,
    pos5_fld_id text,
    pos6_fld_id text,
    pos7_fld_id text,
    pos8_fld_id text,
    pos9_fld_id text,
    base1_run_id text,
    base2_run_id text,
    base3_run_id text,
    event_tx text,
    leadoff_fl boolean,
    ph_fl boolean,
    bat_fld_cd integer,
    bat_lineup_id integer,
    event_cd integer,
    bat_event_fl boolean,
    ab_fl boolean,
    h_cd integer,
    sh_fl boolean,
    sf_fl boolean,
    event_outs_ct integer,
    dp_fl boolean,
    tp_fl boolean,
    rbi_ct integer,
    wp_fl boolean,
    pb_fl boolean,
    fld_cd integer,
    battedball_cd text,
    bunt_fl boolean,
    foul_fl boolean,
    battedball_loc_tx text,
    err_ct integer,
    err1_fld_cd integer,
    err1_cd text,
    err2_fld_cd integer,
    err2_cd text,
    err3_fld_cd integer,
    err3_cd text,
    bat_dest_id integer,
    run1_dest_id integer,
    run2_dest_id integer,
    run3_dest_id integer,
    bat_play_tx text,
    run1_play_tx text,
    run2_play_tx text,
    run3_play_tx text,
    run1_sb_fl boolean,
    run2_sb_fl boolean,
    run3_sb_fl boolean,
    run1_cs_fl boolean,
    run2_cs_fl boolean,
    run3_cs_fl boolean,
    run1_pk_fl boolean,
    run2_pk_fl boolean,
    run3_pk_fl boolean,
    run1_resp_pit_id text,
    run2_resp_pit_id text,
    run3_resp_pit_id text,
    game_new_fl boolean,
    game_end_fl boolean,
    pr_run1_fl boolean,
    pr_run2_fl boolean,
    pr_run3_fl boolean,
    removed_for_pr_run1_id text,
    removed_for_pr_run2_id text,
    removed_for_pr_run3_id text,
    removed_for_ph_bat_id text,
    removed_for_ph_bat_fld_cd integer,
    po1_fld_cd integer,
    po2_fld_cd integer,
    po3_fld_cd integer,
    ass1_fld_cd integer,
    ass2_fld_cd integer,
    ass3_fld_cd integer,
    ass4_fld_cd integer,
    ass5_fld_cd integer,
    event_id integer,
    home_team_id text,
    bat_team_id text,
    fld_team_id text,
    bat_last_id integer,
    inn_new_fl boolean,
    inn_end_fl boolean,
    start_bat_score_ct integer,
    start_fld_score_ct integer,
    inn_runs_ct integer,
    game_pa_ct integer,
    inn_pa_ct integer,
    pa_new_fl boolean,
    pa_trunc_fl boolean,
    start_bases_cd integer,
    end_bases_cd integer,
    bat_start_fl boolean,
    resp_bat_start_fl boolean,
    bat_on_deck_id text,
    bat_in_hold_id text,
    pit_start_fl boolean,
    resp_pit_start_fl boolean,
    run1_fld_cd integer,
    run1_lineup_cd integer,
    run1_origin_event_id integer,
    run2_fld_cd integer,
    run2_lineup_cd integer,
    run2_origin_event_id integer,
    run3_fld_cd integer,
    run3_lineup_cd integer,
    run3_origin_event_id integer,
    run1_resp_cat_id text,
    run2_resp_cat_id text,
    run3_resp_cat_id text,
    pa_ball_ct integer,
    pa_called_ball_ct integer,
    pa_intent_ball_ct integer,
    pa_pitchout_ball_ct integer,
    pa_hitbatter_ball_ct integer,
    pa_other_ball_ct integer,
    pa_strike_ct integer,
    pa_called_strike_ct integer,
    pa_swingmiss_strike_ct integer,
    pa_foul_strike_ct integer,
    pa_inplay_strike_ct integer,
    pa_other_strike_ct integer,
    event_runs_ct integer,
    fld_id text,
    base2_force_fl boolean,
    base3_force_fl boolean,
    base4_force_fl boolean,
    bat_safe_err_fl boolean,
    bat_fate_id integer,
    run1_fate_id integer,
    run2_fate_id integer,
    run3_fate_id integer,
    fate_runs_ct integer,
    ass6_fld_cd integer,
    ass7_fld_cd integer,
    ass8_fld_cd integer,
    ass9_fld_cd integer,
    ass10_fld_cd integer,
    unknown_out_exc_fl boolean,
    uncertain_play_exc_fl boolean,
    count_tx text,
    PRIMARY KEY (season, play_id)
) PARTITION BY RANGE (season);

-- Explicit statements, not a DO block: the pg_duckdb utility hook rejects the DO form in the migration
-- transaction (observed 2026-10-10).
CREATE TABLE core.play_retro_1871 PARTITION OF core.play_retro FOR VALUES FROM (1871) TO (1872);
CREATE TABLE core.play_retro_1872 PARTITION OF core.play_retro FOR VALUES FROM (1872) TO (1873);
CREATE TABLE core.play_retro_1873 PARTITION OF core.play_retro FOR VALUES FROM (1873) TO (1874);
CREATE TABLE core.play_retro_1874 PARTITION OF core.play_retro FOR VALUES FROM (1874) TO (1875);
CREATE TABLE core.play_retro_1875 PARTITION OF core.play_retro FOR VALUES FROM (1875) TO (1876);
CREATE TABLE core.play_retro_1876 PARTITION OF core.play_retro FOR VALUES FROM (1876) TO (1877);
CREATE TABLE core.play_retro_1877 PARTITION OF core.play_retro FOR VALUES FROM (1877) TO (1878);
CREATE TABLE core.play_retro_1878 PARTITION OF core.play_retro FOR VALUES FROM (1878) TO (1879);
CREATE TABLE core.play_retro_1879 PARTITION OF core.play_retro FOR VALUES FROM (1879) TO (1880);
CREATE TABLE core.play_retro_1880 PARTITION OF core.play_retro FOR VALUES FROM (1880) TO (1881);
CREATE TABLE core.play_retro_1881 PARTITION OF core.play_retro FOR VALUES FROM (1881) TO (1882);
CREATE TABLE core.play_retro_1882 PARTITION OF core.play_retro FOR VALUES FROM (1882) TO (1883);
CREATE TABLE core.play_retro_1883 PARTITION OF core.play_retro FOR VALUES FROM (1883) TO (1884);
CREATE TABLE core.play_retro_1884 PARTITION OF core.play_retro FOR VALUES FROM (1884) TO (1885);
CREATE TABLE core.play_retro_1885 PARTITION OF core.play_retro FOR VALUES FROM (1885) TO (1886);
CREATE TABLE core.play_retro_1886 PARTITION OF core.play_retro FOR VALUES FROM (1886) TO (1887);
CREATE TABLE core.play_retro_1887 PARTITION OF core.play_retro FOR VALUES FROM (1887) TO (1888);
CREATE TABLE core.play_retro_1888 PARTITION OF core.play_retro FOR VALUES FROM (1888) TO (1889);
CREATE TABLE core.play_retro_1889 PARTITION OF core.play_retro FOR VALUES FROM (1889) TO (1890);
CREATE TABLE core.play_retro_1890 PARTITION OF core.play_retro FOR VALUES FROM (1890) TO (1891);
CREATE TABLE core.play_retro_1891 PARTITION OF core.play_retro FOR VALUES FROM (1891) TO (1892);
CREATE TABLE core.play_retro_1892 PARTITION OF core.play_retro FOR VALUES FROM (1892) TO (1893);
CREATE TABLE core.play_retro_1893 PARTITION OF core.play_retro FOR VALUES FROM (1893) TO (1894);
CREATE TABLE core.play_retro_1894 PARTITION OF core.play_retro FOR VALUES FROM (1894) TO (1895);
CREATE TABLE core.play_retro_1895 PARTITION OF core.play_retro FOR VALUES FROM (1895) TO (1896);
CREATE TABLE core.play_retro_1896 PARTITION OF core.play_retro FOR VALUES FROM (1896) TO (1897);
CREATE TABLE core.play_retro_1897 PARTITION OF core.play_retro FOR VALUES FROM (1897) TO (1898);
CREATE TABLE core.play_retro_1898 PARTITION OF core.play_retro FOR VALUES FROM (1898) TO (1899);
CREATE TABLE core.play_retro_1899 PARTITION OF core.play_retro FOR VALUES FROM (1899) TO (1900);
CREATE TABLE core.play_retro_1900 PARTITION OF core.play_retro FOR VALUES FROM (1900) TO (1901);
CREATE TABLE core.play_retro_1901 PARTITION OF core.play_retro FOR VALUES FROM (1901) TO (1902);
CREATE TABLE core.play_retro_1902 PARTITION OF core.play_retro FOR VALUES FROM (1902) TO (1903);
CREATE TABLE core.play_retro_1903 PARTITION OF core.play_retro FOR VALUES FROM (1903) TO (1904);
CREATE TABLE core.play_retro_1904 PARTITION OF core.play_retro FOR VALUES FROM (1904) TO (1905);
CREATE TABLE core.play_retro_1905 PARTITION OF core.play_retro FOR VALUES FROM (1905) TO (1906);
CREATE TABLE core.play_retro_1906 PARTITION OF core.play_retro FOR VALUES FROM (1906) TO (1907);
CREATE TABLE core.play_retro_1907 PARTITION OF core.play_retro FOR VALUES FROM (1907) TO (1908);
CREATE TABLE core.play_retro_1908 PARTITION OF core.play_retro FOR VALUES FROM (1908) TO (1909);
CREATE TABLE core.play_retro_1909 PARTITION OF core.play_retro FOR VALUES FROM (1909) TO (1910);
CREATE TABLE core.play_retro_1910 PARTITION OF core.play_retro FOR VALUES FROM (1910) TO (1911);
CREATE TABLE core.play_retro_1911 PARTITION OF core.play_retro FOR VALUES FROM (1911) TO (1912);
CREATE TABLE core.play_retro_1912 PARTITION OF core.play_retro FOR VALUES FROM (1912) TO (1913);
CREATE TABLE core.play_retro_1913 PARTITION OF core.play_retro FOR VALUES FROM (1913) TO (1914);
CREATE TABLE core.play_retro_1914 PARTITION OF core.play_retro FOR VALUES FROM (1914) TO (1915);
CREATE TABLE core.play_retro_1915 PARTITION OF core.play_retro FOR VALUES FROM (1915) TO (1916);
CREATE TABLE core.play_retro_1916 PARTITION OF core.play_retro FOR VALUES FROM (1916) TO (1917);
CREATE TABLE core.play_retro_1917 PARTITION OF core.play_retro FOR VALUES FROM (1917) TO (1918);
CREATE TABLE core.play_retro_1918 PARTITION OF core.play_retro FOR VALUES FROM (1918) TO (1919);
CREATE TABLE core.play_retro_1919 PARTITION OF core.play_retro FOR VALUES FROM (1919) TO (1920);
CREATE TABLE core.play_retro_1920 PARTITION OF core.play_retro FOR VALUES FROM (1920) TO (1921);
CREATE TABLE core.play_retro_1921 PARTITION OF core.play_retro FOR VALUES FROM (1921) TO (1922);
CREATE TABLE core.play_retro_1922 PARTITION OF core.play_retro FOR VALUES FROM (1922) TO (1923);
CREATE TABLE core.play_retro_1923 PARTITION OF core.play_retro FOR VALUES FROM (1923) TO (1924);
CREATE TABLE core.play_retro_1924 PARTITION OF core.play_retro FOR VALUES FROM (1924) TO (1925);
CREATE TABLE core.play_retro_1925 PARTITION OF core.play_retro FOR VALUES FROM (1925) TO (1926);
CREATE TABLE core.play_retro_1926 PARTITION OF core.play_retro FOR VALUES FROM (1926) TO (1927);
CREATE TABLE core.play_retro_1927 PARTITION OF core.play_retro FOR VALUES FROM (1927) TO (1928);
CREATE TABLE core.play_retro_1928 PARTITION OF core.play_retro FOR VALUES FROM (1928) TO (1929);
CREATE TABLE core.play_retro_1929 PARTITION OF core.play_retro FOR VALUES FROM (1929) TO (1930);
CREATE TABLE core.play_retro_1930 PARTITION OF core.play_retro FOR VALUES FROM (1930) TO (1931);
CREATE TABLE core.play_retro_1931 PARTITION OF core.play_retro FOR VALUES FROM (1931) TO (1932);
CREATE TABLE core.play_retro_1932 PARTITION OF core.play_retro FOR VALUES FROM (1932) TO (1933);
CREATE TABLE core.play_retro_1933 PARTITION OF core.play_retro FOR VALUES FROM (1933) TO (1934);
CREATE TABLE core.play_retro_1934 PARTITION OF core.play_retro FOR VALUES FROM (1934) TO (1935);
CREATE TABLE core.play_retro_1935 PARTITION OF core.play_retro FOR VALUES FROM (1935) TO (1936);
CREATE TABLE core.play_retro_1936 PARTITION OF core.play_retro FOR VALUES FROM (1936) TO (1937);
CREATE TABLE core.play_retro_1937 PARTITION OF core.play_retro FOR VALUES FROM (1937) TO (1938);
CREATE TABLE core.play_retro_1938 PARTITION OF core.play_retro FOR VALUES FROM (1938) TO (1939);
CREATE TABLE core.play_retro_1939 PARTITION OF core.play_retro FOR VALUES FROM (1939) TO (1940);
CREATE TABLE core.play_retro_1940 PARTITION OF core.play_retro FOR VALUES FROM (1940) TO (1941);
CREATE TABLE core.play_retro_1941 PARTITION OF core.play_retro FOR VALUES FROM (1941) TO (1942);
CREATE TABLE core.play_retro_1942 PARTITION OF core.play_retro FOR VALUES FROM (1942) TO (1943);
CREATE TABLE core.play_retro_1943 PARTITION OF core.play_retro FOR VALUES FROM (1943) TO (1944);
CREATE TABLE core.play_retro_1944 PARTITION OF core.play_retro FOR VALUES FROM (1944) TO (1945);
CREATE TABLE core.play_retro_1945 PARTITION OF core.play_retro FOR VALUES FROM (1945) TO (1946);
CREATE TABLE core.play_retro_1946 PARTITION OF core.play_retro FOR VALUES FROM (1946) TO (1947);
CREATE TABLE core.play_retro_1947 PARTITION OF core.play_retro FOR VALUES FROM (1947) TO (1948);
CREATE TABLE core.play_retro_1948 PARTITION OF core.play_retro FOR VALUES FROM (1948) TO (1949);
CREATE TABLE core.play_retro_1949 PARTITION OF core.play_retro FOR VALUES FROM (1949) TO (1950);
CREATE TABLE core.play_retro_1950 PARTITION OF core.play_retro FOR VALUES FROM (1950) TO (1951);
CREATE TABLE core.play_retro_1951 PARTITION OF core.play_retro FOR VALUES FROM (1951) TO (1952);
CREATE TABLE core.play_retro_1952 PARTITION OF core.play_retro FOR VALUES FROM (1952) TO (1953);
CREATE TABLE core.play_retro_1953 PARTITION OF core.play_retro FOR VALUES FROM (1953) TO (1954);
CREATE TABLE core.play_retro_1954 PARTITION OF core.play_retro FOR VALUES FROM (1954) TO (1955);
CREATE TABLE core.play_retro_1955 PARTITION OF core.play_retro FOR VALUES FROM (1955) TO (1956);
CREATE TABLE core.play_retro_1956 PARTITION OF core.play_retro FOR VALUES FROM (1956) TO (1957);
CREATE TABLE core.play_retro_1957 PARTITION OF core.play_retro FOR VALUES FROM (1957) TO (1958);
CREATE TABLE core.play_retro_1958 PARTITION OF core.play_retro FOR VALUES FROM (1958) TO (1959);
CREATE TABLE core.play_retro_1959 PARTITION OF core.play_retro FOR VALUES FROM (1959) TO (1960);
CREATE TABLE core.play_retro_1960 PARTITION OF core.play_retro FOR VALUES FROM (1960) TO (1961);
CREATE TABLE core.play_retro_1961 PARTITION OF core.play_retro FOR VALUES FROM (1961) TO (1962);
CREATE TABLE core.play_retro_1962 PARTITION OF core.play_retro FOR VALUES FROM (1962) TO (1963);
CREATE TABLE core.play_retro_1963 PARTITION OF core.play_retro FOR VALUES FROM (1963) TO (1964);
CREATE TABLE core.play_retro_1964 PARTITION OF core.play_retro FOR VALUES FROM (1964) TO (1965);
CREATE TABLE core.play_retro_1965 PARTITION OF core.play_retro FOR VALUES FROM (1965) TO (1966);
CREATE TABLE core.play_retro_1966 PARTITION OF core.play_retro FOR VALUES FROM (1966) TO (1967);
CREATE TABLE core.play_retro_1967 PARTITION OF core.play_retro FOR VALUES FROM (1967) TO (1968);
CREATE TABLE core.play_retro_1968 PARTITION OF core.play_retro FOR VALUES FROM (1968) TO (1969);
CREATE TABLE core.play_retro_1969 PARTITION OF core.play_retro FOR VALUES FROM (1969) TO (1970);
CREATE TABLE core.play_retro_1970 PARTITION OF core.play_retro FOR VALUES FROM (1970) TO (1971);
CREATE TABLE core.play_retro_1971 PARTITION OF core.play_retro FOR VALUES FROM (1971) TO (1972);
CREATE TABLE core.play_retro_1972 PARTITION OF core.play_retro FOR VALUES FROM (1972) TO (1973);
CREATE TABLE core.play_retro_1973 PARTITION OF core.play_retro FOR VALUES FROM (1973) TO (1974);
CREATE TABLE core.play_retro_1974 PARTITION OF core.play_retro FOR VALUES FROM (1974) TO (1975);
CREATE TABLE core.play_retro_1975 PARTITION OF core.play_retro FOR VALUES FROM (1975) TO (1976);
CREATE TABLE core.play_retro_1976 PARTITION OF core.play_retro FOR VALUES FROM (1976) TO (1977);
CREATE TABLE core.play_retro_1977 PARTITION OF core.play_retro FOR VALUES FROM (1977) TO (1978);
CREATE TABLE core.play_retro_1978 PARTITION OF core.play_retro FOR VALUES FROM (1978) TO (1979);
CREATE TABLE core.play_retro_1979 PARTITION OF core.play_retro FOR VALUES FROM (1979) TO (1980);
CREATE TABLE core.play_retro_1980 PARTITION OF core.play_retro FOR VALUES FROM (1980) TO (1981);
CREATE TABLE core.play_retro_1981 PARTITION OF core.play_retro FOR VALUES FROM (1981) TO (1982);
CREATE TABLE core.play_retro_1982 PARTITION OF core.play_retro FOR VALUES FROM (1982) TO (1983);
CREATE TABLE core.play_retro_1983 PARTITION OF core.play_retro FOR VALUES FROM (1983) TO (1984);
CREATE TABLE core.play_retro_1984 PARTITION OF core.play_retro FOR VALUES FROM (1984) TO (1985);
CREATE TABLE core.play_retro_1985 PARTITION OF core.play_retro FOR VALUES FROM (1985) TO (1986);
CREATE TABLE core.play_retro_1986 PARTITION OF core.play_retro FOR VALUES FROM (1986) TO (1987);
CREATE TABLE core.play_retro_1987 PARTITION OF core.play_retro FOR VALUES FROM (1987) TO (1988);
CREATE TABLE core.play_retro_1988 PARTITION OF core.play_retro FOR VALUES FROM (1988) TO (1989);
CREATE TABLE core.play_retro_1989 PARTITION OF core.play_retro FOR VALUES FROM (1989) TO (1990);
CREATE TABLE core.play_retro_1990 PARTITION OF core.play_retro FOR VALUES FROM (1990) TO (1991);
CREATE TABLE core.play_retro_1991 PARTITION OF core.play_retro FOR VALUES FROM (1991) TO (1992);
CREATE TABLE core.play_retro_1992 PARTITION OF core.play_retro FOR VALUES FROM (1992) TO (1993);
CREATE TABLE core.play_retro_1993 PARTITION OF core.play_retro FOR VALUES FROM (1993) TO (1994);
CREATE TABLE core.play_retro_1994 PARTITION OF core.play_retro FOR VALUES FROM (1994) TO (1995);
CREATE TABLE core.play_retro_1995 PARTITION OF core.play_retro FOR VALUES FROM (1995) TO (1996);
CREATE TABLE core.play_retro_1996 PARTITION OF core.play_retro FOR VALUES FROM (1996) TO (1997);
CREATE TABLE core.play_retro_1997 PARTITION OF core.play_retro FOR VALUES FROM (1997) TO (1998);
CREATE TABLE core.play_retro_1998 PARTITION OF core.play_retro FOR VALUES FROM (1998) TO (1999);
CREATE TABLE core.play_retro_1999 PARTITION OF core.play_retro FOR VALUES FROM (1999) TO (2000);
CREATE TABLE core.play_retro_2000 PARTITION OF core.play_retro FOR VALUES FROM (2000) TO (2001);
CREATE TABLE core.play_retro_2001 PARTITION OF core.play_retro FOR VALUES FROM (2001) TO (2002);
CREATE TABLE core.play_retro_2002 PARTITION OF core.play_retro FOR VALUES FROM (2002) TO (2003);
CREATE TABLE core.play_retro_2003 PARTITION OF core.play_retro FOR VALUES FROM (2003) TO (2004);
CREATE TABLE core.play_retro_2004 PARTITION OF core.play_retro FOR VALUES FROM (2004) TO (2005);
CREATE TABLE core.play_retro_2005 PARTITION OF core.play_retro FOR VALUES FROM (2005) TO (2006);
CREATE TABLE core.play_retro_2006 PARTITION OF core.play_retro FOR VALUES FROM (2006) TO (2007);
CREATE TABLE core.play_retro_2007 PARTITION OF core.play_retro FOR VALUES FROM (2007) TO (2008);
CREATE TABLE core.play_retro_2008 PARTITION OF core.play_retro FOR VALUES FROM (2008) TO (2009);
CREATE TABLE core.play_retro_2009 PARTITION OF core.play_retro FOR VALUES FROM (2009) TO (2010);
CREATE TABLE core.play_retro_2010 PARTITION OF core.play_retro FOR VALUES FROM (2010) TO (2011);
CREATE TABLE core.play_retro_2011 PARTITION OF core.play_retro FOR VALUES FROM (2011) TO (2012);
CREATE TABLE core.play_retro_2012 PARTITION OF core.play_retro FOR VALUES FROM (2012) TO (2013);
CREATE TABLE core.play_retro_2013 PARTITION OF core.play_retro FOR VALUES FROM (2013) TO (2014);
CREATE TABLE core.play_retro_2014 PARTITION OF core.play_retro FOR VALUES FROM (2014) TO (2015);
CREATE TABLE core.play_retro_2015 PARTITION OF core.play_retro FOR VALUES FROM (2015) TO (2016);
CREATE TABLE core.play_retro_2016 PARTITION OF core.play_retro FOR VALUES FROM (2016) TO (2017);
CREATE TABLE core.play_retro_2017 PARTITION OF core.play_retro FOR VALUES FROM (2017) TO (2018);
CREATE TABLE core.play_retro_2018 PARTITION OF core.play_retro FOR VALUES FROM (2018) TO (2019);
CREATE TABLE core.play_retro_2019 PARTITION OF core.play_retro FOR VALUES FROM (2019) TO (2020);
CREATE TABLE core.play_retro_2020 PARTITION OF core.play_retro FOR VALUES FROM (2020) TO (2021);
CREATE TABLE core.play_retro_2021 PARTITION OF core.play_retro FOR VALUES FROM (2021) TO (2022);
CREATE TABLE core.play_retro_2022 PARTITION OF core.play_retro FOR VALUES FROM (2022) TO (2023);
CREATE TABLE core.play_retro_2023 PARTITION OF core.play_retro FOR VALUES FROM (2023) TO (2024);
CREATE TABLE core.play_retro_2024 PARTITION OF core.play_retro FOR VALUES FROM (2024) TO (2025);
CREATE TABLE core.play_retro_2025 PARTITION OF core.play_retro FOR VALUES FROM (2025) TO (2026);
CREATE TABLE core.play_retro_2026 PARTITION OF core.play_retro FOR VALUES FROM (2026) TO (2027);
CREATE TABLE core.play_retro_2027 PARTITION OF core.play_retro FOR VALUES FROM (2027) TO (2028);
CREATE TABLE core.play_retro_default PARTITION OF core.play_retro DEFAULT;

-- MLB-API-only fields on core.play (nullable; NULL for Retrosheet rows).
ALTER TABLE core.play
    ADD COLUMN IF NOT EXISTS description text,
    ADD COLUMN IF NOT EXISTS batter_name text,
    ADD COLUMN IF NOT EXISTS pitcher_name text,
    ADD COLUMN IF NOT EXISTS bat_side text,
    ADD COLUMN IF NOT EXISTS pitch_hand text,
    ADD COLUMN IF NOT EXISTS rbi integer,
    ADD COLUMN IF NOT EXISTS batter_mlbam_id bigint,
    ADD COLUMN IF NOT EXISTS pitcher_mlbam_id bigint;
