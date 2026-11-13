// Run with playwright 1.62.1 installed. Test data are synthetic demo text only.
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

(async () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'siling-ui-'));
  const ready = path.join(temporary, 'ready.json');
  const child = spawn(process.env.PYTHON || 'python', ['-m', 'siling_voice', 'serve', '--demo', '--no-browser', '--port', '0', '--ready-file', ready], {
    env: {...process.env, SILING_CONFIG_DIR: path.join(temporary, 'config')}, stdio: ['ignore', 'inherit', 'inherit']
  });
  let browser;
  try {
    const until = Date.now() + 15000;
    while (!fs.existsSync(ready)) {
      if (Date.now() > until || child.exitCode !== null) throw new Error('UI service startup failed');
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const info = JSON.parse(fs.readFileSync(ready, 'utf8'));
    browser = await chromium.launch({headless: true});
    const page = await browser.newPage({viewport: {width: 1000, height: 1050}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${info.url}/#token=${info.token}`);
    await page.getByRole('button', {name:'开始监听', exact:true}).click();
    await page.getByRole('heading', {name:'等待唤醒', exact:true}).waitFor();
    await page.getByRole('button', {name:'手动唤醒', exact:true}).click();
    await page.getByText('这是模拟演示文本，未进行真实语音识别。', {exact:true}).waitFor();
    fs.mkdirSync('.evidence', {recursive:true});
    await page.screenshot({path:'.evidence/ui-desktop.png', fullPage:true});
    await page.getByRole('button', {name:'静音并释放麦克风', exact:true}).click();
    await page.getByRole('heading', {name:'麦克风已释放', exact:true}).waitFor();
    if (await page.getByText('这是模拟演示文本，未进行真实语音识别。', {exact:true}).count()) throw new Error('Transcript not cleared');
    await page.setViewportSize({width:390, height:844});
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Horizontal overflow');
    await page.screenshot({path:'.evidence/ui-mobile.png', fullPage:true});
    await page.getByText('麦克风与唤醒设置', {exact:true}).click();
    await page.getByLabel('中文唤醒词', {exact:true}).fill('小爱同学');
    await page.getByRole('button', {name:'保存设置并停止监听', exact:true}).click();
    await page.getByText('开始监听后，说「小爱同学」', {exact:true}).waitFor();
    await page.getByText('AI 与播报设置', {exact:true}).click();
    await page.getByLabel('对话服务', {exact:true}).selectOption('mock');
    await page.getByLabel('中文播报', {exact:true}).selectOption('mock');
    await page.getByRole('button', {name:'保存 AI 与播报设置', exact:true}).click();
    for (let turn = 1; turn <= 3; turn++) {
      await page.getByLabel('文字消息', {exact:true}).fill('中文对话测试');
      await page.getByRole('button', {name:'发送', exact:true}).click();
      await page.getByText(`这是第${turn}轮模拟回复。真实 AI 服务尚未调用。`, {exact:true}).waitFor();
    }
    await page.getByText('工具、权限与桌面', {exact:true}).click();
    const project = path.join(temporary, 'project'); fs.mkdirSync(project);
    await page.getByLabel('目标类型', {exact:true}).selectOption('folders');
    await page.getByLabel('目标 ID', {exact:true}).fill('project');
    await page.getByLabel('语音名称', {exact:true}).fill('项目目录');
    await page.getByLabel('完整路径', {exact:true}).fill(project);
    await page.getByRole('button', {name:'加入配置列表', exact:true}).click();
    await page.getByRole('button', {name:'保存白名单', exact:true}).click();
    await page.getByLabel('文字消息', {exact:true}).fill('打开项目目录');
    await page.getByRole('button', {name:'发送', exact:true}).click();
    await page.locator('.tool-approval').waitFor();
    await page.getByRole('button', {name:'拒绝', exact:true}).click();
    await page.getByText('操作已取消或无法执行。', {exact:true}).waitFor();
    await page.getByRole('button', {name:'完全退出司聆', exact:true}).click();
    await page.getByRole('alert').filter({hasText:'司聆已退出'}).waitFor();
    if (errors.length) throw new Error(errors.join('\n'));
    console.log('PASS: desktop/mobile UI, wake demo, clear, settings, exit; 0 page errors');
  } catch(error) {
    if (browser) {const pages = browser.contexts().flatMap(c => c.pages()); if (pages[0]) {await pages[0].screenshot({path:".evidence/ui-failure.png",fullPage:true}); fs.writeFileSync(".evidence/ui-failure.html",await pages[0].content());}}
    throw error;
  } finally {
    if (browser) await browser.close();
    if (child.exitCode === null) child.kill();
    fs.rmSync(temporary, {recursive:true, force:true});
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
