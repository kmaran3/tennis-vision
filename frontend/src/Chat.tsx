import React,{useEffect,useRef,useState} from 'react';
import Markdown from 'react-markdown';
import {readChatStream} from './chat-stream';
import './chat.css';
type Row=Record<string,any>;
type Turn={question:string;answer:string;result?:Row;error?:string;complete:boolean};
function Logo({thinking=false}:{thinking?:boolean}){return <span className={'chat-logo'+(thinking?' is-thinking':'')} aria-hidden="true">◒</span>}
export function Chat({tour,surface,end,Evidence}:{tour:string;surface:string;end:string;Evidence:React.ComponentType<{evidence:Row[]}>}){
 const [auth,setAuth]=useState<Row>({}),[question,setQuestion]=useState(''),[turns,setTurns]=useState<Turn[]>([]),[busy,setBusy]=useState(false),[status,setStatus]=useState(''),[error,setError]=useState('');
 const controller=useRef<AbortController|null>(null),stopReason=useRef(''),scroll=useRef<HTMLDivElement>(null),follow=useRef(true),input=useRef<HTMLTextAreaElement>(null);
 useEffect(()=>{let active=true;fetch('/api/v1/auth/me').then(r=>r.json()).then(value=>{if(active)setAuth(value)}).catch(()=>{if(active)setError('Could not check sign-in. Refresh to try again.')});return()=>{active=false;controller.current?.abort();}},[]);
 useEffect(()=>{if(follow.current&&scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight},[turns,status]);
 function patch(update:Partial<Turn>){setTurns(old=>old.map((turn,i)=>i===old.length-1?{...turn,...update}:turn))}
 async function send(text:string){
  text=text.trim();if(!text||controller.current)return;
  const history=turns.filter(t=>t.complete).slice(-5).flatMap(t=>[{role:'user',content:t.question},{role:'assistant',content:t.answer.slice(0,8000)}]);
  while(history.reduce((n,m)=>n+m.content.length,0)>16000)history.splice(0,2);
  const abort=new AbortController();controller.current=abort;stopReason.current='';follow.current=true;
  setQuestion('');setError('');setTurns(old=>[...old,{question:text,answer:'',complete:false}]);setBusy(true);setStatus('Connecting to Baseline…');
  const deadline=window.setTimeout(()=>{stopReason.current='Baseline took too long to respond. Please try again.';abort.abort()},55000);
  try{
   const response=await fetch('/api/v1/analyst/stream',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',signal:abort.signal,body:JSON.stringify({question:text,history,tour,surface:surface||null,end:end||null})});
   let draft='';
   await readChatStream(response,(event,data)=>{
    if(event==='status')setStatus(data.message);
    if(event==='reset'){draft='';patch({answer:''})}
    if(event==='delta'){draft+=data.text;patch({answer:draft});setStatus('Writing your answer…')}
    if(event==='done')patch({answer:data.data.answer,result:data,complete:true});
    if(event==='error')throw new Error(data.message||'Baseline could not finish. Please retry.');
   });
  }catch(reason){const message=abort.signal.aborted?(stopReason.current||'Response stopped. You can retry or ask another question.'):(reason as Error).message;patch({error:message});setError(message);}
  finally{window.clearTimeout(deadline);controller.current=null;setBusy(false);setStatus('');input.current?.focus();}
 }
 function submit(e:React.FormEvent){e.preventDefault();void send(question)}
 return <><div className="analyst-intro"><Logo/><h2>What are you curious about?</h2><p>Your tennis conversation starts here. Explore the archive, compare players,<br/>or ask a follow-up. Numbers come with their source context.</p></div>
 <section className="panel chat-panel" aria-label="Ask Baseline">
  <div className="chat-top"><div><Logo/><strong>Baseline</strong><span>Tennis, with context.</span></div><button className="text-button" type="button" disabled={busy||!turns.length} onClick={()=>{setTurns([]);setError('');input.current?.focus()}}>New chat</button></div>
  {turns.length>0?<div className="chat-transcript" role="log" aria-label="Conversation" aria-live="off" ref={scroll} onScroll={()=>{const el=scroll.current;if(el)follow.current=el.scrollHeight-el.scrollTop-el.clientHeight<90}}>
   {turns.map((turn,i)=><React.Fragment key={i}><article className="chat-message chat-user"><span className="chat-speaker">You</span><div>{turn.question}</div></article><article className="chat-message chat-assistant" aria-busy={busy&&i===turns.length-1}><span className="chat-speaker"><Logo thinking={busy&&i===turns.length-1}/>Baseline</span>{turn.answer&&<div className={'answer'+(busy&&i===turns.length-1?' is-writing':'')}><Markdown>{turn.answer}</Markdown></div>}{busy&&i===turns.length-1&&<div className="thinking-status" role="status"><Logo thinking/>{status}</div>}{turn.complete&&turn.result&&<><Evidence evidence={turn.result.data.evidence}/>{turn.result.data.evidence.length>0&&<details><summary>Sources & tool evidence</summary><pre>{JSON.stringify(turn.result.data.evidence,null,2)}</pre></details>}<p className="chat-provenance">{turn.result.data.model} · {turn.result.data.tool_calls} tools · {turn.result.filters?.tour||tour} cutoff {turn.result.cutoffs?.find((c:Row)=>c.tour===(turn.result!.filters?.tour||tour))?.cutoff||'see evidence'}</p></>}{turn.error&&<p className="chat-interrupted">{turn.answer?'Partial response · ':''}{turn.error}</p>}</article></React.Fragment>)}
  </div>:<div className="chat-welcome"><p>Hi, I’m Baseline. Let’s talk tennis.</p><span>Historical players, surfaces, matchups and the numbers behind them.</span><div className="chat-starters">{['What can you help me with?','Explain surface Elo','Compare first-serve win rates by surface'].map(text=><button type="button" key={text} disabled={!auth.approved} onClick={()=>void send(text)}>{text} ↗</button>)}</div></div>}
  <div className="sr-only" role="status">{busy?'Baseline is responding.':turns.at(-1)?.complete?'Baseline response complete.':''}</div>
  {error&&<div className="chat-error" role="alert">{error}{turns.length>0&&<button type="button" className="text-button" disabled={busy} onClick={()=>void send(turns.at(-1)!.question)}>Retry question</button>}</div>}
  <form className="chat-composer" onSubmit={submit}><label htmlFor="question">Your tennis question</label><textarea ref={input} id="question" rows={2} maxLength={4000} value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(!busy&&auth.approved)void send(question)}}} placeholder={turns.length?'Ask a follow-up…':'Ask about a player, a matchup, or a tennis concept…'}/><div className="form-row"><small>5 tools / turn · 20 turns / user / UTC day · 100 app-wide</small>{busy?<button type="button" className="chat-stop" onClick={()=>{stopReason.current='Response stopped. You can retry or ask another question.';controller.current?.abort()}}>■ Stop response</button>:auth.approved?<button className="primary" disabled={!question.trim()}>Ask Baseline ↗</button>:<a className="primary" href="/api/v1/auth/login">Sign in with GitHub ↗</a>}</div></form>
  {!auth.approved&&<p className="panel-note">Live chat is available to the owner and explicitly approved GitHub users. Browsing and model predictions are public.</p>}
 </section></>;
}
