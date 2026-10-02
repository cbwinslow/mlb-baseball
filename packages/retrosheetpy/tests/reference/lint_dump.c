/* Runs cw_game_lint on every game of an event file and prints, per game, the stderr messages
 * (redirected to stdout, unbuffered) and the result. Compiled against the real Chadwick sources;
 * lint_dump.py prints the same from the port. */
#include <stdio.h>
#include <unistd.h>
#include "chadwick.h"
int main(int argc,char**argv){
  FILE *fp=fopen(argv[1],"r"); CWGame *g;
  setvbuf(stdout,NULL,_IONBF,0); dup2(1,2);
  while((g=cw_game_read(fp))){ printf("GAME %s\n",g->game_id); printf("lint=%d\n",cw_game_lint(g)); }
  return 0; }
