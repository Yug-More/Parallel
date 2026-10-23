const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, 'parallel-frontend/node_modules/playwright'));
const bundle = process.env.MERMAID_BUNDLE;
if (!bundle) throw new Error('Set MERMAID_BUNDLE to the installed mermaid/dist/mermaid.min.js path');
(async () => {
  const files = ['README.md', ...fs.readdirSync(path.join(root,'docs')).filter(x => x.endsWith('.md')).map(x => 'docs/'+x)];
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.addScriptTag({path:bundle});
  await page.evaluate(() => mermaid.initialize({startOnLoad:false,securityLevel:'strict'}));
  let diagrams = 0;
  for (const file of files) {
    const content = fs.readFileSync(path.join(root,file),'utf8');
    for (const match of content.matchAll(/```mermaid\n([\s\S]*?)```/g)) {
      diagrams++;
      await page.evaluate(async ({source,id}) => { await mermaid.parse(source); await mermaid.render('diagram'+id,source); },{source:match[1],id:diagrams});
      process.stdout.write(file+' diagram '+diagrams+' parsed and rendered\n');
    }
    for (const match of content.matchAll(/(?:!?\[[^\]]*\])\(([^)]+)\)/g)) {
      const target = match[1].split('#')[0];
      if (!target || /^(https?:|mailto:)/.test(target)) continue;
      if (!fs.existsSync(path.resolve(root,path.dirname(file),target))) throw new Error('Missing local link: '+file+' -> '+target);
    }
  }
  await browser.close();
  process.stdout.write(diagrams+' Mermaid diagrams validated\n');
})().catch(error => { process.stderr.write(error.stack+'\n');process.exit(1); });
