// Run against a local server in DEMO mode with a disposable data directory.
// npm --prefix frontend install; npx --prefix frontend playwright install chromium
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium}=process.env.PLAYWRIGHT_MODULE?require(process.env.PLAYWRIGHT_MODULE):require('@playwright/test');
const base=process.env.QP_BASE_URL||'http://127.0.0.1:8000';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1050}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);
 await page.getByRole('heading',{name:'Know what can ship.'}).waitFor();
 await page.getByRole('button',{name:'Load demo inbox'}).click();
 await page.waitForFunction(async()=>{const r=await fetch('/api/cases');const cases=await r.json();return cases.length>=9&&cases.every(c=>c.state==='complete');},{},{timeout:60000});
 await page.getByRole('button',{name:/demo-02.*a discrepancy/i}).click();
 await page.getByRole('heading',{name:'The seven-field check'}).waitFor();
 const weight=page.getByRole('row').filter({hasText:'Gross weight'});
 assert.match(await weight.innerText(),/Difference/);
 await weight.getByRole('button').last().click();
 await page.getByRole('heading',{name:'draft.txt',exact:true}).waitFor();
 assert.match(await page.locator('.source-block.highlight').innerText(),/12.8 MT/);
 await page.getByRole('button',{name:'Close',exact:true}).click();
 await mkdir(new URL('../test-results/',import.meta.url),{recursive:true});
 await page.screenshot({path:new URL('../test-results/inbox-desktop.png',import.meta.url).pathname,fullPage:true});
 await page.getByRole('button',{name:/demo-03.*value that needs review/i}).click();
 await page.getByText('Human review required',{exact:true}).waitFor();
 await page.locator('summary').filter({hasText:'Review actions'}).click();
 assert.equal(await page.getByRole('button',{name:'Acknowledge report'}).isDisabled(),true);
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:new URL('../test-results/inbox-mobile.png',import.meta.url).pathname,fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'Mobile viewport must not overflow');
 assert.deepEqual(errors,[]);
 console.log('PASS: demo import, comparison, source evidence, review approval guard, desktop/mobile rendering; no browser exceptions.');
}finally{await browser.close();}
