/* Prints every field of the CWBoxscore that cw_box_create builds for each game of an event file.
 * Compiled against the real Chadwick sources; box_dump.py prints the same from the port. */
#include <stdio.h>
#include <string.h>
#include "chadwick.h"
static void s(const char *p){ if(!p){printf("~");return;} for(;*p;p++){unsigned char c=*p; if(c<32||c>126||c=='\\'||c=='|') printf("\\x%02x",c); else putchar(c);} }
#define X(f) printf("%d ", o->f)
static void bat(CWBoxBatting *o){ printf(" bat "); X(g);X(pa);X(ab);X(r);X(h);X(b2);X(b3);X(hr);X(hrslam);X(bi);X(bi2out);X(gw);X(bb);X(ibb);X(so);X(gdp);X(hp);X(sh);X(sf);X(sb);X(cs);X(xi);X(lisp);X(movedup);X(pitches);X(strikes); printf("\n"); }
static void fld(CWBoxFielding *o){ printf(" fld "); if(!o){printf("~\n");return;} X(g);X(outs);X(bip);X(bf);X(po);X(a);X(e);X(dp);X(tp);X(pb);X(xi); printf("\n"); }
static void pit(CWBoxPitching *o){ printf(" pit "); X(g);X(gs);X(cg);X(sho);X(gf);X(outs);X(ab);X(r);X(er);X(h);X(b2);X(b3);X(hr);X(hrslam);X(bb);X(ibb);X(so);X(bf);X(bk);X(wp);X(hb);X(gdp);X(sh);X(sf);X(xi);X(pk);X(w);X(l);X(sv);X(inr);X(inrs);X(xb);X(xbinn);X(gb);X(fb);X(pitches);X(strikes); printf("\n"); }
#undef X
static void player(CWBoxPlayer *p){
  printf("player "); s(p->player_id); printf("|"); s(p->name); printf("|"); s(p->date); printf("|ph=%d pr=%d np=%d sp=%d pos=", p->ph_inn,p->pr_inn,p->num_positions,p->start_position);
  for(int i=0;i<p->num_positions && i<40;i++) printf("%d,",p->positions[i]);
  printf("\n"); bat(p->batting); for(int i=0;i<10;i++) fld(p->fielding[i]);
}
static void evlist(const char *k, CWBoxEvent *e){
  for(;e;e=e->next){ printf("%s in=%d h=%d r=%d po=%d o=%d m=%d loc=",k,e->inning,e->half_inning,e->runners,e->pickoff,e->outs,e->mark); s(e->location); printf(" pl=");
    for(int i=0;i<20;i++){ s(e->players[i]); printf(","); } printf("\n"); }
}
static void box(CWBoxscore *b){
  for(int t=0;t<2;t++){
    for(int i=0;i<10;i++){ CWBoxPlayer *p=b->slots[i][t]; if(!p) continue; while(p->prev) p=p->prev; printf("slot %d %d\n",i,t); for(;p;p=p->next) player(p); }
    CWBoxPitcher *q=b->pitchers[t]; if(q){ while(q->prev) q=q->prev; for(;q;q=q->next){ printf("pitcher %d ",t); s(q->player_id); printf("|"); s(q->name); printf("\n"); pit(q->pitching);} }
    printf("line %d:",t); for(int i=0;i<50;i++) printf("%d,",b->linescore[i][t]); printf("\n");
    printf("tot %d score=%d hits=%d err=%d dp=%d tp=%d lob=%d er=%d ra=%d rh=%d\n",t,b->score[t],b->hits[t],b->errors[t],b->dp[t],b->tp[t],b->lob[t],b->er[t],b->risp_ab[t],b->risp_h[t]);
  }
  printf("end outs=%d walkoff=%d\n",b->outs_at_end,b->walk_off);
  evlist("b2",b->b2_list);evlist("b3",b->b3_list);evlist("hr",b->hr_list);evlist("sb",b->sb_list);evlist("cs",b->cs_list);evlist("po",b->po_list);
  evlist("sh",b->sh_list);evlist("sf",b->sf_list);evlist("hp",b->hp_list);evlist("ibb",b->ibb_list);evlist("wp",b->wp_list);evlist("bk",b->bk_list);
  evlist("err",b->err_list);evlist("pb",b->pb_list);evlist("dp",b->dp_list);evlist("tp",b->tp_list);
}
int main(int argc,char**argv){
  FILE *fp=fopen(argv[1],"r"); CWGame *g;
  while((g=cw_game_read(fp))){ printf("BOX "); s(g->game_id); printf("\n"); fflush(stdout); CWBoxscore *b=cw_box_create(g); box(b); fflush(stdout); }
  return 0; }
