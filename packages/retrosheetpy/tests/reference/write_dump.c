/* Reads a file with Chadwick, applies a script of edits, writes it back with Chadwick's writers.
 * usage: write_dump FILE MODE [SCRIPT]   MODE = game | book | roster | league
 * Script: one op per line, tab-separated fields (see write_dump.py for the same interpreter). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "chadwick.h"

static int split(char *line, char **f) {
  int n = 0; char *p = line;
  f[n++] = p;
  for (; *p; p++) if (*p == '\t') { *p = 0; f[n++] = p + 1; if (n >= 32) break; }
  return n;
}

static void game_op(CWGame *g, char **f, int n) {
  const char *op = f[0];
  if (!strcmp(op, "version")) cw_game_set_version(g, f[1]);
  else if (!strcmp(op, "info_append")) cw_game_info_append(g, f[1], f[2]);
  else if (!strcmp(op, "info_set")) cw_game_info_set(g, f[1], f[2]);
  else if (!strcmp(op, "starter")) cw_game_starter_append(g, f[1], f[2], atoi(f[3]), atoi(f[4]), atoi(f[5]));
  else if (!strcmp(op, "event")) cw_game_event_append(g, atoi(f[1]), atoi(f[2]), f[3], f[4], f[5], f[6]);
  else if (!strcmp(op, "sub")) cw_game_substitute_append(g, f[1], f[2], atoi(f[3]), atoi(f[4]), atoi(f[5]));
  else if (!strcmp(op, "data")) cw_game_data_append(g, n - 1, f + 1);
  else if (!strcmp(op, "stat")) cw_game_stat_append(g, n - 1, f + 1);
  else if (!strcmp(op, "evdata")) cw_game_evdata_append(g, n - 1, f + 1);
  else if (!strcmp(op, "line")) cw_game_line_append(g, n - 1, f + 1);
  else if (!strcmp(op, "set_er")) cw_game_data_set_er(g, f[1], atoi(f[2]));
  else if (!strcmp(op, "comment")) { char *t = strdup(f[1]); cw_game_comment_append(g, t); }
  else if (!strcmp(op, "evcomment")) { if (g->last_event) cw_event_comment_append(g->last_event, f[1]); }
  else if (!strcmp(op, "replace")) cw_game_replace_player(g, f[1], f[2]);
  else if (!strcmp(op, "truncate")) {
    int k = atoi(f[1]); CWEvent *e = g->first_event;
    while (e && k-- > 0) e = e->next;
    if (e) cw_game_truncate(g, e);
  }
  else if (!strcmp(op, "badj")) { if (g->last_event) { g->last_event->batter_hand = f[1][0]; } }
  else if (!strcmp(op, "padj")) { if (g->last_event) { g->last_event->pitcher_hand = f[1][0]; g->last_event->pitcher_hand_id = strdup(f[2]); } }
  else if (!strcmp(op, "ladj")) { if (g->last_event) { g->last_event->ladj_align = atoi(f[1]); g->last_event->ladj_slot = atoi(f[2]); } }
  else if (!strcmp(op, "radj")) { if (g->last_event) { g->last_event->auto_runner_id = strdup(f[1]); g->last_event->auto_base = atoi(f[2]); } }
}

static void load(const char *path, int *count, char ****rows, int **ns) {
  FILE *fp = fopen(path, "r"); static char buf[1 << 16]; int cap = 0; *count = 0; *rows = NULL; *ns = NULL;
  if (!fp) return;
  while (fgets(buf, sizeof buf, fp)) {
    char *nl = strchr(buf, '\n'); if (nl) *nl = 0;
    char **f = malloc(sizeof(char *) * 32);
    int n = split(strdup(buf), f);
    if (*count == cap) { cap = cap ? cap * 2 : 16; *rows = realloc(*rows, sizeof(char **) * cap); *ns = realloc(*ns, sizeof(int) * cap); }
    (*rows)[*count] = f; (*ns)[*count] = n; (*count)++;
  }
}

int main(int argc, char **argv) {
  FILE *fp = fopen(argv[1], "r"); const char *mode = argv[2];
  int count = 0; char ***rows = NULL; int *ns = NULL;
  if (argc > 3) load(argv[3], &count, &rows, &ns);
  if (!strcmp(mode, "game")) {
    CWGame *g;
    while ((g = cw_game_read(fp))) {
      for (int i = 0; i < count; i++) game_op(g, rows[i], ns[i]);
      cw_game_write(g, stdout);
    }
  } else if (!strcmp(mode, "book")) {
    CWScorebook *b = cw_scorebook_create();
    int n = cw_scorebook_read(b, fp);
    if (n < 0) { printf("read=-1\n"); return 0; }
    for (int i = 0; i < count; i++) {
      char **f = rows[i];
      if (!strcmp(f[0], "reshuffle")) {   /* remove all games, rotated by f[1], re-insert in that order */
        int k = atoi(f[1]), rev = atoi(f[2]), m = 0; CWGame *gs[100000], *out[100000];
        for (CWGame *g = b->first_game; g; g = g->next) gs[m++] = g;
        char **ids = malloc(sizeof(char *) * (m + 1));
        for (int j = 0; j < m; j++) ids[j] = strdup(gs[(j + k) % (m ? m : 1)]->game_id);
        if (rev) for (int a = 0, z = m - 1; a < z; a++, z--) { char *t = ids[a]; ids[a] = ids[z]; ids[z] = t; }
        for (int j = 0; j < m; j++) out[j] = cw_scorebook_remove_game(b, ids[j]);
        for (int j = 0; j < m; j++) cw_scorebook_insert_game(b, out[j]);
      } else if (!strcmp(f[0], "remove")) { cw_scorebook_remove_game(b, f[1]); }
    }
    cw_scorebook_write(b, stdout);
  } else if (!strcmp(mode, "roster")) {
    CWRoster *r = cw_roster_create("T", 0, "L", "C", "N"); cw_roster_read(r, fp);
    for (int i = 0; i < count; i++) {
      char **f = rows[i];
      if (!strcmp(f[0], "insert")) cw_roster_player_insert(r, cw_player_create(f[1], f[2], f[3], f[4][0], f[5][0]));
      else if (!strcmp(f[0], "append")) cw_roster_player_append(r, cw_player_create(f[1], f[2], f[3], f[4][0], f[5][0]));
      else if (!strcmp(f[0], "first")) { CWPlayer *p = cw_roster_player_find(r, f[1]); if (p) cw_player_set_first_name(p, f[2]); }
      else if (!strcmp(f[0], "last")) { CWPlayer *p = cw_roster_player_find(r, f[1]); if (p) cw_player_set_last_name(p, f[2]); }
      else if (!strcmp(f[0], "city")) cw_roster_set_city(r, f[1]);
      else if (!strcmp(f[0], "nick")) cw_roster_set_nickname(r, f[1]);
      else if (!strcmp(f[0], "league")) cw_roster_set_league(r, f[1]);
    }
    cw_roster_write(r, stdout);
    printf("count=%d city=%s nick=%s league=%s\n", cw_roster_player_count(r), r->city, r->nickname, r->league);
  } else if (!strcmp(mode, "league")) {
    CWLeague *l = cw_league_create(); cw_league_read(l, fp);
    for (int i = 0; i < count; i++)
      if (!strcmp(rows[i][0], "append")) cw_league_roster_append(l, cw_roster_create(rows[i][1], 0, rows[i][2], rows[i][3], rows[i][4]));
    cw_league_write(l, stdout);
  }
  return 0;
}
