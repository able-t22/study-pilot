/* Optional browser regression. Start StudyPilot, then set UI_TEST_URL and PLAYWRIGHT_MODULE. */
const assert=require('node:assert/strict');
const pw=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const base=process.env.UI_TEST_URL;
 assert(base,'Set UI_TEST_URL to an isolated running StudyPilot test server with a learner and course material.');
 const browser=await pw.chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>r.request().url().startsWith(base)?r.continue():r.abort());
  await page.goto(base);
  await page.waitForFunction(()=>document.querySelector('#mode').textContent.length>0);
  await page.evaluate(()=>{closeModal();show('notes');});
  await page.waitForSelector('#n_styles button');
  await page.locator('#n_focus').fill('Remember my focus');
  for(let i=0;i<7;i++){
   await page.locator('#n_styles button').nth(i).click();
   assert.equal(await page.locator('#n_styles button[aria-pressed=true]').count(),1);
   assert.equal(await page.locator('#n_focus').inputValue(),'Remember my focus');
  }
  await page.evaluate(()=>show('revise'));
  await page.waitForSelector('#revout .revt');
  assert.equal(await page.locator('.card.revt').evaluate(e=>getComputedStyle(e).display),'block');
  for(const id of ['revise','eval'])assert.equal(await page.locator('#'+id).evaluate(e=>e.parentElement.tagName),'MAIN');
  const formulas='\\[\\text{Mean squared error}=\\frac{1}{n}\\sum_{i=1}^{n}(y_i-\\hat{y}_i)^2\\]\nInline \\(\\sqrt{25}=5\\), legacy /sqrt{16}, matrix \\(\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\\).';
  await page.evaluate(t=>{let e=document.createElement('div');e.id='math-regression';e.innerHTML=mdNotes(t);document.querySelector('#revout').append(e);renderMath(e);},formulas);
  assert.equal(await page.locator('#math-regression math').count(),4);
  assert.equal(await page.locator('#math-regression mfrac').count(),1);
  assert.equal(await page.locator('#math-regression msqrt').count(),2);
  assert.equal(await page.locator('#math-regression mtable mtr').count(),2);
  assert.equal(await page.locator('#math-regression mtext').textContent(),'Mean squared error');
  await page.evaluate(()=>show('eval'));
  const pos=await page.locator('#eval').evaluate(e=>({x:e.getBoundingClientRect().x,w:e.getBoundingClientRect().width}));
  assert(pos.x>248&&pos.w>900);
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.body.scrollWidth<=innerWidth));
  await page.route('**/api/languages',r=>r.fulfill({status:500,body:'{}',contentType:'application/json'}));
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#lang option[value=en]'));
  assert(!await page.locator('#mode').textContent().then(x=>/Backend unavailable/.test(x)));
  assert.deepEqual(errors,[]);
  console.log('UI REGRESSIONS OK: note styles, revision, Evaluation, offline maths, mobile width and independent connection status');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
