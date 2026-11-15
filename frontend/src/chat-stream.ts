/** Incremental UTF-8 SSE parser. Network chunks need not align with events or characters. */
export async function readChatStream(response:Response,onEvent:(event:string,data:any)=>void){
 if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail?.message||'Baseline could not connect. Please try again.');}
 if(!response.body)throw new Error('Streaming is unavailable in this browser.');
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',ended=false;
 function consume(){let boundary:number;while((boundary=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);let event='message';const data:string[]=[];for(const line of block.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))data.push(line.slice(5).trimStart());}if(data.length){const value=JSON.parse(data.join('\n'));onEvent(event,value);if(event==='done'||event==='error')ended=true;}}}
 try{while(!ended){const {done,value}=await reader.read();buffer=(buffer+decoder.decode(value,{stream:!done})).replace(/\r\n/g,'\n');consume();if(done)break;}if(!ended)throw new Error('The connection ended before the answer finished. Please retry.');}
 finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
