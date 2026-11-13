const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../inventario_casa/static/js/app.js'), 'utf8');
new vm.Script(source); // Parse the entire shipped frontend, not just the harness.
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[m]));
const decode = s => s.replace(/&(amp|lt|gt|quot|#39);/g, (_, e) => ({amp:'&', lt:'<', gt:'>', quot:'"', '#39':"'"}[e]));
const calls = [];
let listener;
const context = vm.createContext({
  esc, t: s => s, tf: s => s, Number, alert: message => {throw Error(message);},
  document: {addEventListener: (name, cb) => {assert.equal(name, 'click'); listener = cb;}},
  S: {groupOffsets: {}, groupHasMore: {}, subgroupOffsets: {}, subgroupHasMore: {}},
  subgroupCacheKey: (a,b) => a+'::'+b,
});
for (const kind of ['Group', 'Subgroup']) {
  for (const action of ['First', 'Previous', 'More', 'Last']) {
    const name = 'load'+action+kind;
    context[name] = (...args) => {calls.push({name,args}); return Promise.resolve();};
  }
}
function extract(start, end) {
  const a = source.indexOf(start);
  const b = source.indexOf(end, a);
  assert.ok(a >= 0 && b > a);
  return source.slice(a,b);
}
vm.runInContext(extract('function renderLoadMore(', 'function subgroupCacheKey('), context);
vm.runInContext(extract('function renderSubgroupLoadMore(', 'function renderTypeSubgroups('), context);
const marker = source.indexOf('// Delegation preserves apostrophes');
assert.ok(marker >= 0);
vm.runInContext(source.slice(marker), context);
assert.equal(typeof listener, 'function');

const key = `L'attacco "speciale" \\ <tag> & ');throw Error('injected');//`;
for (const subgroup of [false,true]) {
  let markup;
  if (subgroup) {
    const cache = context.subgroupCacheKey('7',key);
    context.S.subgroupOffsets[cache] = 50;
    context.S.subgroupHasMore[cache] = true;
    markup = context.renderSubgroupLoadMore('7',key,50,150);
  } else {
    context.S.groupOffsets[key] = 50;
    context.S.groupHasMore[key] = true;
    markup = context.renderLoadMore(key,50,150);
  }
  const buttons = [...markup.matchAll(/<button\b([^>]*)>/g)];
  assert.equal(buttons.length,4);
  for (const [,attrs] of buttons) {
    assert.ok(!attrs.includes('onclick='));
    const dataset = {};
    for (const [,name,value] of attrs.matchAll(/data-([\w-]+)="([^"]*)"/g)) {
      dataset[name.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = decode(value);
    }
    let stopped = false;
    const event = {target: {closest: () => ({dataset})}, stopPropagation: () => {stopped = true;}};
    listener(event);
    assert.ok(stopped);
    const call = calls.at(-1);
    const fn = {first:'First', previous:'Previous', next:'More', last:'Last'}[dataset.pageAction];
    assert.equal(call.name, 'load'+fn+(subgroup ? 'Subgroup' : 'Group'));
    const expected = subgroup ? ['7',key] : [key];
    if (dataset.pageAction === 'last') expected.push(150);
    expected.push(event);
    assert.deepEqual(call.args, expected);
  }
}
assert.equal(calls.length,8);
console.log('PASS: 8 pagination actions preserve special characters; full frontend syntax valid.');
