#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include "chadwick.h"
static char out[8192]; static int n;
#define P(...) (n += snprintf(out + n, sizeof(out) - n, __VA_ARGS__))
static void str(const char *p){ for(;*p;p++){unsigned char c=*p; if(c<32||c>126||c=='\\') P("\\x%02x",c); else P("%c",c);} }
static void ints(const char *k,int *a,int len){ P("%s=",k); for(int i=0;i<len;i++) P("%d,",a[i]); P("|"); }
int main(void){
  char line[4096];
  while(fgets(line,sizeof line,stdin)){
    line[strcspn(line,"\n")]=0;
    fflush(stdout);
    pid_t pid=fork();
    if(pid==0){
      char text[4096]; strcpy(text,line);
      CWEventData e; memset(&e,0xAA,sizeof e);
      int ok=cw_parse_event(text,&e);
      n=0; P("ok=%d|type=%d|",ok,e.event_type);
      ints("adv",e.advance,4); ints("rbi",e.rbi_flag,4); ints("fc",e.fc_flag,4); ints("muff",e.muff_flag,4);
      for(int i=0;i<4;i++){P("play%d=",i); str(e.play[i]); P("|");}
      P("sh=%d|sf=%d|dp=%d|gdp=%d|tp=%d|wp=%d|pb=%d|foul=%d|bunt=%d|force=%d|",e.sh_flag,e.sf_flag,e.dp_flag,e.gdp_flag,e.tp_flag,e.wp_flag,e.pb_flag,e.foul_flag,e.bunt_flag,e.force_flag);
      ints("sb",e.sb_flag+1,3); ints("cs",e.cs_flag+1,3); ints("po",e.po_flag+1,3);
      P("fby=%d|np=%d|na=%d|ne=%d|nt=%d|",e.fielded_by,e.num_putouts,e.num_assists,e.num_errors,e.num_touches);
      ints("put",e.putouts,3); ints("ast",e.assists,10); ints("err",e.errors,10); ints("tch",e.touches,19);
      P("et="); for(int i=0;i<10;i++) P("%c",e.error_types[i]); P("|bbt=%d|hl=",e.batted_ball_type); str(e.hit_location);
      P("\n"); write(1,out,n); _exit(0);
    }
    int st; waitpid(pid,&st,0);
    if(!WIFEXITED(st)||WEXITSTATUS(st)!=0) printf("UB\n");
  }
  return 0; }
