"""Exact constant-serve scoring probabilities, with rule-aware final sets."""
from dataclasses import dataclass, field
from functools import lru_cache

@dataclass(frozen=True)
class Rules:
    best_of: int = 3
    final_tiebreak_at: int | None = 6
    final_tiebreak_target: int = 7
    source: str = "standard tiebreak sets"


def slam_rules(event,year,tour):
    event=event.lower().replace(" ","").replace("rolandgarros","frenchopen")
    if event not in ("ausopen","australianopen","frenchopen","wimbledon","usopen"):raise ValueError("Unknown scoring rules")
    best=5 if tour=="ATP" else 3
    if year>=2022:return Rules(best,6,10,"Grand Slam unified final-set rule, 2022 onward")
    if event=="usopen":return Rules(best,6,7,"US Open final-set tiebreak")
    if event in ("ausopen","australianopen") and year>=2019:return Rules(best,6,10,"Australian Open 2019–2021")
    if event=="wimbledon" and year>=2019:return Rules(best,12,7,"Wimbledon 2019–2021")
    return Rules(best,None,7,"Historical Grand Slam advantage final set")


@lru_cache(maxsize=65536)
def game_win(p,a=0,b=0):
    if a>=4 and a-b>=2:return 1.0
    if b>=4 and b-a>=2:return 0.0
    if a>=3 and b>=3:
        deuce=p*p/(p*p+(1-p)*(1-p))
        if a==b:return deuce
        return p+(1-p)*deuce if a>b else p*deuce
    return p*game_win(p,a+1,b)+(1-p)*game_win(p,a,b+1)


def tb_server(first,n):
    return first if n==0 or ((n-1)//2)%2==1 else 1-first


def tiebreak_win(s1,s2,first,a=0,b=0,target=7):
    @lru_cache(None)
    def calc(a,b):
        if max(a,b)>=target and abs(a-b)>=2:return float(a>b)
        if min(a,b)>=target-1:
            win=s1*(1-s2);lose=(1-s1)*s2;tie=win/(win+lose)
            if a==b:return tie
            p=s1 if tb_server(first,a+b)==0 else 1-s2
            return p+(1-p)*tie if a>b else p*tie
        p=s1 if tb_server(first,a+b)==0 else 1-s2
        return p*calc(a+1,b)+(1-p)*calc(a,b+1)
    return calc(a,b)

@dataclass
class State:
    rules: Rules
    server: int = 0
    sets: list[int] = field(default_factory=lambda:[0,0])
    games: list[int] = field(default_factory=lambda:[0,0])
    points: list[int] = field(default_factory=lambda:[0,0])
    tb_first: int | None = None

    @property
    def finished(self):return max(self.sets)>self.rules.best_of//2
    def tb_at(self):return self.rules.final_tiebreak_at if sum(self.sets)==self.rules.best_of-1 else 6
    def target(self):return self.rules.final_tiebreak_target if sum(self.sets)==self.rules.best_of-1 else 7
    def is_tiebreak(self):return self.tb_at() is not None and self.games==[self.tb_at(),self.tb_at()]
    def advance(self,winner):
        if self.finished:raise ValueError("Point after match completed")
        tb=self.is_tiebreak()
        if tb and self.tb_first is None:self.tb_first=self.server
        self.points[winner]+=1
        end=max(self.points)>=(self.target() if tb else 4) and abs(self.points[0]-self.points[1])>=2
        if not end:
            if tb:self.server=tb_server(self.tb_first,sum(self.points))
            return
        self.games[winner]+=1;self.points=[0,0]
        self.server=1-(self.tb_first if tb else self.server)
        set_end=tb or (max(self.games)>=6 and abs(self.games[0]-self.games[1])>=2)
        if set_end:self.sets[winner]+=1;self.games=[0,0];self.tb_first=None

    def label(self):
        if self.is_tiebreak():p=self.points
        elif min(self.points)>=3:p=["AD" if self.points[0]>self.points[1] else "40","AD" if self.points[1]>self.points[0] else "40"]
        else:p=[(0,15,30,40)[min(x,3)] for x in self.points]
        return f"{self.sets[0]}–{self.sets[1]} sets · {self.games[0]}–{self.games[1]} · {p[0]}–{p[1]}"

    def probability(self,s1=0.63,s2=0.60):
        holds=(game_win(s1),1-game_win(s2))
        @lru_cache(None)
        def set_outcomes(g1,g2,server,final):
            at=self.rules.final_tiebreak_at if final else 6
            target=self.rules.final_tiebreak_target if final else 7
            if max(g1,g2)>=6 and abs(g1-g2)>=2:return {(int(g2>g1),server):1.0}
            if at is not None and g1==g2==at:
                p=tiebreak_win(s1,s2,server,target=target);return {(0,1-server):p,(1,1-server):1-p}
            if at is None and g1==g2 and g1>=5:
                win=holds[0]*holds[1];lose=(1-holds[0])*(1-holds[1]);p=win/(win+lose)
                return {(0,server):p,(1,server):1-p}
            result={};p=holds[server]
            for a,b,weight in ((g1+1,g2,p),(g1,g2+1,1-p)):
                for key,value in set_outcomes(a,b,1-server,final).items():result[key]=result.get(key,0)+weight*value
            return result
        @lru_cache(None)
        def match(a,b,server):
            if max(a,b)>self.rules.best_of//2:return float(a>b)
            return sum(p*match(a+(w==0),b+(w==1),next_server) for (w,next_server),p in set_outcomes(0,0,server,a+b==self.rules.best_of-1).items())
        if self.finished:return float(self.sets[0]>self.sets[1])
        a,b=self.sets;g1,g2=self.games
        if self.is_tiebreak():
            p=tiebreak_win(s1,s2,self.tb_first if self.tb_first is not None else self.server,*self.points,target=self.target())
            nxt=1-(self.tb_first if self.tb_first is not None else self.server)
            return p*match(a+1,b,nxt)+(1-p)*match(a,b+1,nxt)
        point_p=s1 if self.server==0 else 1-s2
        p=game_win(point_p,*self.points)
        total=0.0
        for ga,gb,weight in ((g1+1,g2,p),(g1,g2+1,1-p)):
            total+=weight*sum(v*match(a+(w==0),b+(w==1),nxt) for (w,nxt),v in set_outcomes(ga,gb,1-self.server,a+b==self.rules.best_of-1).items())
        return total
