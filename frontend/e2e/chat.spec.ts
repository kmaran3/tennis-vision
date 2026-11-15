import {test,expect} from '@playwright/test';
import {createServer,type Server} from 'node:http';
let server:Server,endpoint:string;
const requests:any[]=[];
test.beforeAll(async()=>{
 server=createServer((req,res)=>{let raw='';req.on('data',chunk=>raw+=chunk);req.on('end',()=>{
  const body=JSON.parse(raw);requests.push(body);
  res.writeHead(200,{'Content-Type':'text/event-stream','Access-Control-Allow-Origin':'*'});
  const emit=(event:string,data:unknown)=>res.write(`event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`);
  emit('status',{message:'Thinking about your tennis question…'});
  const fail=body.question==='timeout fixture'&&requests.filter(r=>r.question==='timeout fixture').length===1;
  const stop=body.question==='stop fixture';
  const first=setTimeout(()=>{if(fail){emit('error',{code:'provider_timeout',message:'The AI took too long to respond. Please retry.'});res.end();return;}emit('delta',{text:'Clay gives'});},600);
  const last=setTimeout(()=>{
   const answer=body.history.length?'On clay, the serve needs more placement.':'Clay gives returners more time. Tennis 🎾';
   emit('reset',{});
   // Split a multibyte character and CRLF across network writes.
   const chunk=Buffer.from(`event: delta\r\ndata: ${JSON.stringify({text:answer})}\r\n\r\n`),split=chunk.indexOf(Buffer.from('🎾'))+2;
   res.write(chunk.subarray(0,split));
   setTimeout(()=>{res.write(chunk.subarray(split));emit('done',{data:{answer,evidence:[],model:'offline-browser-fixture',tool_calls:0},cutoffs:[{tour:'ATP',cutoff:'2026-05-25'}],filters:{tour:'ATP'}});res.end();},100);
  },stop?15000:1600);
  res.on('close',()=>{clearTimeout(first);clearTimeout(last)});
 });});
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
 endpoint=`http://127.0.0.1:${(server.address() as {port:number}).port}/stream`;
});
test.afterAll(async()=>{await new Promise<void>(resolve=>server.close(()=>resolve()))});
test.beforeEach(async({page})=>{
 requests.length=0;
 await page.route('**/api/v1/auth/me',route=>route.fulfill({json:{login:'owner',approved:true}}));
 await page.addInitScript(url=>{const original=window.fetch;window.fetch=(input,init)=>String(input)==='/api/v1/analyst/stream'?original(url,{...init,headers:{'Content-Type':'text/plain'},credentials:'omit'}):original(input,init)},endpoint);
});
test('thinking logo, incremental text, UTF-8, and conversational history',async({page})=>{
 await page.goto('/ask?tour=ATP');await page.getByLabel('Your tennis question').fill('Why does clay change tennis?');await page.getByRole('button',{name:'Ask Baseline ↗'}).click();
 await expect(page.locator('.thinking-status .is-thinking')).toBeVisible();
 await expect(page.getByRole('button',{name:'Stop response'})).toBeVisible();
 await page.screenshot({path:'../artifacts/baseline-thinking.png',fullPage:true});
 await expect(page.locator('.answer')).toHaveText('Clay gives');
 await expect(page.locator('.answer')).toHaveText('Clay gives returners more time. Tennis 🎾');
 await expect(page.getByRole('button',{name:'Stop response'})).toHaveCount(0);
 await page.getByLabel('Your tennis question').fill('And the serve?');await page.getByLabel('Your tennis question').press('Enter');
 await expect(page.locator('.answer').last()).toHaveText('On clay, the serve needs more placement.');
 expect(requests[1].history).toEqual([{role:'user',content:'Why does clay change tennis?'},{role:'assistant',content:'Clay gives returners more time. Tennis 🎾'}]);
 await page.screenshot({path:'../artifacts/baseline-conversation.png',fullPage:true});
});
test('terminal provider error can be retried without sending failed history',async({page})=>{
 await page.goto('/ask');await page.getByLabel('Your tennis question').fill('timeout fixture');await page.getByRole('button',{name:'Ask Baseline ↗'}).click();
 await expect(page.getByRole('alert')).toContainText('too long');
 await page.getByRole('button',{name:'Retry question'}).click();await expect(page.locator('.answer').last()).toContainText('Tennis 🎾');
 expect(requests[1].history).toEqual([]);
});
test('stop releases UI immediately; reduced motion and mobile layout',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
 await page.goto('/ask');await page.getByLabel('Your tennis question').fill('stop fixture');await page.getByRole('button',{name:'Ask Baseline ↗'}).click();
 const logo=page.locator('.thinking-status .is-thinking');await expect(logo).toBeVisible();
 expect(await logo.evaluate(el=>getComputedStyle(el).animationName)).toBe('none');
 await page.getByRole('button',{name:'Stop response'}).click();await expect(page.getByRole('alert')).toContainText('Response stopped');
 await expect(page.getByRole('button',{name:'Ask Baseline ↗'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('dropdown menu uses theme and supports keyboard selection and escape',async({page})=>{
 await page.goto('/explore?tour=ATP');const surface=page.getByRole('combobox',{name:'Surface',exact:true});
 await surface.focus();await page.keyboard.press('Enter');await expect(page.getByRole('listbox')).toBeVisible();
 expect(await page.getByRole('listbox').evaluate(el=>getComputedStyle(el.closest('.select-menu')!).backgroundColor)).toBe('rgb(255, 254, 248)');
 await page.keyboard.press('c');await expect(page.getByRole('option',{name:'Clay',exact:true})).toBeFocused();await page.keyboard.press('Enter');await expect(surface).toHaveText('Clay⌄');
 await surface.press('Enter');await page.keyboard.press('Escape');await expect(surface).toBeFocused();
 await expect(page.locator('select:visible')).toHaveCount(0);
});
