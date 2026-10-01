#include <stdio.h>
#include <string.h>
#include "chadwick.h"
static void s(const char *p){ if(!p){printf("~");return;} for(;*p;p++){unsigned char c=*p; if(c<32||c>126||c=='\\'||c=='|') printf("\\x%02x",c); else putchar(c);} }
static void f(const char *l,const char *p){ printf("%s=",l); s(p); printf("|"); }
static void app(const char *k, CWAppearance *a){ for(;a;a=a->next){ printf("%s ",k); f("id",a->player_id); f("n",a->name); printf("t=%d|s=%d|p=%d\n",a->team,a->slot,a->pos);} }
static void com(CWComment *c){ for(;c;c=c->next){ printf("com "); f("t",c->text); f("e0",c->ejection.person_id); f("e1",c->ejection.person_role); f("e2",c->ejection.umpire_id); f("e3",c->ejection.reason); f("u0",c->umpchange.inning); f("u1",c->umpchange.position); f("u2",c->umpchange.person_id); printf("\n"); } }
static void dat(const char *k, CWData *d){ for(;d;d=d->next){ printf("%s n=%d ",k,d->num_data); for(int i=0;i<d->num_data;i++){s(d->data[i]);printf(",");} printf("\n"); } }
int main(int argc,char**argv){
  FILE *fp=fopen(argv[1],"r"); CWGame *g;
  while((g=cw_game_read(fp))){
    printf("GAME "); f("id",g->game_id); f("v",g->version); printf("\n");
    for(CWInfo*i=g->first_info;i;i=i->next){printf("info ");f("l",i->label);f("d",i->data);printf("\n");}
    app("start",g->first_starter); com(g->first_comment);
    dat("data",g->first_data); dat("stat",g->first_stat); dat("evdata",g->first_evdata); dat("line",g->first_line);
    for(CWEvent*e=g->first_event;e;e=e->next){
      printf("ev %d %d ",e->inning,e->batting_team); f("b",e->batter);f("c",e->count);f("p",e->pitches);f("e",e->event_text);
      printf("bh=%d|ph=%d|",e->batter_hand,e->pitcher_hand); f("phid",e->pitcher_hand_id);
      printf("la=%d|ls=%d|ab=%d|",e->ladj_align,e->ladj_slot,e->auto_base); f("ar",e->auto_runner_id);
      for(int k=0;k<4;k++){f("pa",e->presadj[k]);} printf("\n");
      app("sub",e->first_sub); com(e->first_comment);
    }
  }
  return 0; }
