const http = require('http');
const { URL } = require('url');

const HOST = '127.0.0.1';
const PORT = Number(process.env.WEBUI_PORT || 29100);
const CORE_PORT = Number(process.env.CORE_PORT || 29090);
const CORE = `http://127.0.0.1:${CORE_PORT}`;
const GROUP = 'Tyty';
const TEST_URL = 'https://www.google.com/generate_204';

// The browser talks to this small local proxy so Mihomo needs no CORS changes.
const page = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Tyty Node Selector</title>
  <style>
    :root { color-scheme: light; font-family: Inter, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #20242b; background: #f5f6f8; }
    header { background: #fff; border-bottom: 1px solid #dfe3e8; }
    .bar { max-width: 1120px; margin: auto; padding: 18px 20px; display: flex; gap: 16px; align-items: center; justify-content: space-between; }
    h1 { margin: 0; font-size: 20px; font-weight: 650; }
    .status { font-size: 14px; color: #59636f; overflow-wrap: anywhere; }
    main { max-width: 1120px; margin: auto; padding: 20px; }
    .toolbar { display: grid; grid-template-columns: minmax(180px, 1fr) auto auto auto; gap: 10px; margin-bottom: 14px; }
    input, button, select { height: 38px; border: 1px solid #cbd1d8; background: #fff; color: inherit; border-radius: 6px; font: inherit; }
    input { width: 100%; padding: 0 12px; }
    button, select { padding: 0 13px; cursor: pointer; }
    button.primary { background: #315b9d; border-color: #315b9d; color: #fff; }
    button:disabled { cursor: wait; opacity: .58; }
    .summary { margin: 0 0 12px; color: #59636f; font-size: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
    .node { min-height: 82px; padding: 12px; background: #fff; border: 1px solid #dfe3e8; border-radius: 6px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
    .node.current { border-color: #315b9d; box-shadow: inset 3px 0 #315b9d; }
    .name { min-width: 0; font-size: 14px; overflow-wrap: anywhere; }
    .latency { min-width: 64px; text-align: right; font-variant-numeric: tabular-nums; color: #68727e; }
    .latency.ok { color: #18864b; }
    .latency.slow { color: #b66a00; }
    .latency.error { color: #c93535; }
    .actions { grid-column: 1 / -1; display: flex; gap: 8px; }
    .actions button { height: 30px; padding: 0 10px; font-size: 13px; }
    @media (max-width: 620px) { .toolbar { grid-template-columns: 1fr 1fr; } .toolbar input { grid-column: 1 / -1; } }
  </style>
</head>
<body>
  <header><div class="bar"><h1>Tyty Node Selector</h1><div id="status" class="status">Connecting...</div></div></header>
  <main>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Search nodes">
      <select id="mode" title="Proxy mode"><option value="rule">Rule</option><option value="global">Global</option></select>
      <select id="sort"><option value="original">Original order</option><option value="delay">Latency</option><option value="name">Name</option></select>
      <button id="testAll" class="primary">Test all</button>
    </div>
    <p id="summary" class="summary"></p>
    <div id="grid" class="grid"></div>
  </main>
  <script>
    let state = { now: '', mode: 'rule', connected: false, nodes: [], delays: new Map(), testing: new Set() };
    const el = id => document.getElementById(id);
    const api = async (path, options) => {
      const r = await fetch(path, options);
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    };
    const delayText = name => {
      const d = state.delays.get(name);
      if (state.testing.has(name)) return ['Testing', ''];
      if (d === undefined) return ['Not tested', ''];
      if (!d) return ['Error', 'error'];
      return [d + ' ms', d < 300 ? 'ok' : 'slow'];
    };
    function render() {
      const q = el('search').value.trim().toLowerCase();
      let nodes = state.nodes.filter(n => n.toLowerCase().includes(q));
      if (el('sort').value === 'delay') nodes.sort((a,b) => (state.delays.get(a)||999999) - (state.delays.get(b)||999999));
      if (el('sort').value === 'name') nodes.sort((a,b) => a.localeCompare(b));
      el('status').textContent = state.now ? 'Current: ' + state.now : 'Core unavailable';
      el('mode').value = state.mode;
      el('mode').disabled = !state.connected;
      const working = [...state.delays.values()].filter(Boolean).length;
      el('summary').textContent = nodes.length + ' nodes' + (state.delays.size ? ', ' + working + ' responding' : '');
      el('grid').replaceChildren(...nodes.map(name => {
        const card = document.createElement('div'); card.className = 'node' + (name === state.now ? ' current' : '');
        const title = document.createElement('div'); title.className = 'name'; title.textContent = name;
        const latency = document.createElement('div'); const [text, cls] = delayText(name); latency.className = 'latency ' + cls; latency.textContent = text;
        const actions = document.createElement('div'); actions.className = 'actions';
        const use = document.createElement('button'); use.textContent = name === state.now ? 'Selected' : 'Use'; use.disabled = name === state.now;
        use.onclick = async () => { use.disabled = true; await api('/api/select', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}); state.now=name; render(); };
        const test = document.createElement('button'); test.textContent = 'Test'; test.disabled = state.testing.has(name);
        test.onclick = () => testOne(name);
        actions.append(use,test); card.append(title,latency,actions); return card;
      }));
    }
    async function testOne(name) {
      state.testing.add(name); render();
      try { const r = await api('/api/delay?name=' + encodeURIComponent(name)); state.delays.set(name, r.delay || 0); }
      catch { state.delays.set(name, 0); }
      state.testing.delete(name); render();
    }
    async function testAll() {
      const button=el('testAll'); button.disabled=true; state.delays.clear();
      let index=0; const workers=Array.from({length:8}, async()=>{ while(index<state.nodes.length) await testOne(state.nodes[index++]); });
      await Promise.all(workers); button.disabled=false; render();
    }
    async function load() {
      try {
        const [group, config] = await Promise.all([api('/api/group'), api('/api/config')]);
        state.now=group.now; state.nodes=group.all||[]; state.mode=config.mode || 'rule'; state.connected=true; render();
      }
      catch(e) { el('status').textContent='Start the Tyty Wine core first'; }
    }
    async function setMode() {
      const select = el('mode'); const mode = select.value; select.disabled = true;
      try { await api('/api/mode', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})}); state.mode=mode; }
      catch(e) { alert('Could not change proxy mode: ' + e.message); }
      render();
    }
    el('search').oninput=render; el('sort').onchange=render; el('mode').onchange=setMode; el('testAll').onclick=testAll; load();
  </script>
</body>
</html>`;

async function core(path, options) {
  const response = await fetch(CORE + path, options);
  const text = await response.text();
  if (!response.ok) throw new Error(text || response.statusText);
  return text ? JSON.parse(text) : {};
}

// Only loopback is used; the controller and node credentials stay local.
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${HOST}:${PORT}`);
    res.setHeader('Cache-Control', 'no-store');
    if (url.pathname === '/') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      return res.end(page);
    }
    if (url.pathname === '/api/group') {
      return json(res, await core('/proxies/' + encodeURIComponent(GROUP)));
    }
    if (url.pathname === '/api/config') {
      return json(res, await core('/configs'));
    }
    if (url.pathname === '/api/mode' && req.method === 'POST') {
      const body = await readJson(req);
      if (!['rule', 'global'].includes(body.mode)) {
        res.statusCode = 400;
        return res.end('Unsupported proxy mode');
      }
      await core('/configs', {
        method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: body.mode})
      });
      return json(res, {ok: true, mode: body.mode});
    }
    if (url.pathname === '/api/select' && req.method === 'POST') {
      const body = await readJson(req);
      await core('/proxies/' + encodeURIComponent(GROUP), {
        method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: body.name})
      });
      return json(res, {ok: true});
    }
    if (url.pathname === '/api/delay') {
      const name = url.searchParams.get('name');
      const path = '/proxies/' + encodeURIComponent(name) + '/delay?timeout=10000&url=' + encodeURIComponent(TEST_URL);
      return json(res, await core(path));
    }
    res.statusCode = 404; res.end('Not found');
  } catch (error) {
    res.statusCode = 502;
    res.end(error.message);
  }
});

function json(res, value) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(value));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', chunk => data += chunk);
    req.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
    req.on('error', reject);
  });
}

server.listen(PORT, HOST, () => console.log(`Tyty WebUI: http://${HOST}:${PORT}`));
