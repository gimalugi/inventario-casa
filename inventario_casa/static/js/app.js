
let S={types:[],items:[],suggestions:{},counts:{},groups:[],groupItems:{},groupHasMore:{},groupOffsets:{},subgroups:{},subgroupItems:{},subgroupHasMore:{},subgroupOffsets:{},matched_count:0,page_size:50};
let editingItem=null, editingType=null, viewingItem=null;

const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

const LANGUAGE_STORAGE_KEY='inventario_language';

function detectInitialLanguage(){
  // 1. Preferenza scelta manualmente dall'utente.
  const saved=localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if(saved && window.INVENTORY_I18N[saved]) return saved;

  // 2. Lingua predefinita configurata nell'add-on.
  const configured=(window.INVENTORY_DEFAULT_LANGUAGE||'').toLowerCase();
  if(configured && window.INVENTORY_I18N[configured]) return configured;

  // 3. Lingua dell'interfaccia Home Assistant, quando accessibile.
  try{
    if(window.parent && window.parent!==window){
      const haLanguage=(
        window.parent.document.documentElement.lang||''
      ).toLowerCase();

      if(haLanguage.startsWith('it')) return 'it';
      if(haLanguage.startsWith('en')) return 'en';
    }
  }catch(e){
    // L'accesso al documento padre può essere bloccato:
    // in quel caso usiamo normalmente la lingua del browser.
  }

  // 4. Lingua del browser/dispositivo.
  const browserLanguage=(navigator.language||'it').toLowerCase();

  if(browserLanguage.startsWith('it')) return 'it';
  if(browserLanguage.startsWith('en')) return 'en';

  // 5. Lingua predefinita per quelle non ancora supportate.
  return 'it';
}

let currentLanguage=detectInitialLanguage();

function t(key){
  return window.INVENTORY_I18N[currentLanguage]?.[key] ??
         window.INVENTORY_I18N.it[key] ??
         key;
}

function tf(key,vars={}){
  return t(key).replace(/\{(\w+)\}/g,(_,name)=>
    Object.prototype.hasOwnProperty.call(vars,name) ? vars[name] : `{${name}}`
  );
}

function applyLanguage(){
  document.documentElement.lang=currentLanguage;

  document.querySelectorAll('[data-i18n]').forEach(el=>{
    const key=el.dataset.i18n;
    el.textContent=t(key);
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(el=>{
    const key=el.dataset.i18nPlaceholder;
    el.placeholder=t(key);
  });

  document.querySelectorAll('[data-i18n-title]').forEach(el=>{
    const key=el.dataset.i18nTitle;
    el.title=t(key);
  });

  document.querySelectorAll('[data-i18n-alt]').forEach(el=>{
    el.alt=t(el.dataset.i18nAlt);
  });

  document.querySelectorAll('[data-i18n-aria-label]').forEach(el=>{
    const key=el.dataset.i18nAriaLabel;
    el.setAttribute('aria-label',t(key));
  });

  const selector=$('languageSelect');
  if(selector) selector.value=currentLanguage;
}

function setLanguage(language){
  if(!window.INVENTORY_I18N[language]) return;

  currentLanguage=language;
  localStorage.setItem(LANGUAGE_STORAGE_KEY,language);
  applyLanguage();

  // Rigenera i contenuti creati dinamicamente senza ricaricare i dati.
  if(typeof S !== 'undefined' && S && S.counts){
    render();
  }
}

function withPageSize(url){
  if(!url.startsWith('api/inventory-'))return url;

  const sep=url.includes('?') ? '&' : '?';

  if(/[?&]page_size=/.test(url))return url;

  return url+sep+'page_size='+encodeURIComponent(getPageSize());
}

async function api(path,opts={}){
  path=withPageSize(path);
  const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
  const d=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(d.error||t('error'));
  return d;
}


/* v2.2.1 - sincronizzazione colori dal tema Home Assistant.
   Nessun polling: viene eseguita al caricamento e quando la pagina
   torna visibile/in primo piano. */
const homeAssistantThemeVars=[
  '--primary-background-color',
  '--secondary-background-color',
  '--card-background-color',
  '--primary-text-color',
  '--secondary-text-color',
  '--primary-color',
  '--accent-color',
  '--divider-color',
  '--input-fill-color',
  '--lovelace-background',
  '--app-header-background-color',
  '--sidebar-background-color',
  '--ha-font-family-body',
  '--ha-font-family-heading',
  '--paper-font-common-base_-_font-family'
];

function syncHomeAssistantTheme(){
  const root=document.documentElement;
  let found=0;

  try{
    if(window.parent===window){
      root.classList.remove('ha-theme-linked');
      return false;
    }

    const parentRoot=window.parent.document.documentElement;
    const parentStyle=window.parent.getComputedStyle(parentRoot);

    for(const name of homeAssistantThemeVars){
      const value=parentStyle.getPropertyValue(name).trim();
      if(value){
        root.style.setProperty(name,value);
        found++;
      }
    }

    root.classList.toggle('ha-theme-linked',found>=3);
    return found>=3;
  }catch(e){
    root.classList.remove('ha-theme-linked');
    return false;
  }
}

const PAGE_SIZE_ALLOWED=[10,50,100];

function getPageSize(){
  const saved=Number(localStorage.getItem('inventario_page_size') || 50);
  return PAGE_SIZE_ALLOWED.includes(saved) ? saved : 50;
}

async function setPageSize(value){
  const size=Number(value);
  if(!PAGE_SIZE_ALLOWED.includes(size))return;

  localStorage.setItem('inventario_page_size',String(size));
  S.page_size=size;

  await load();
}

function syncPageSizeSetting(){
  const select=$('pageSizeSelect');
  if(select)select.value=String(getPageSize());
}

let searchDebounceTimer=null;

function updateSearchClear(){
  const input=$('search');
  const clear=$('searchClear');
  if(!input || !clear)return;

  clear.classList.toggle('show',input.value.length>0);

  clearTimeout(searchDebounceTimer);
  searchDebounceTimer=setTimeout(()=>{
    load();
  },500);
}

async function clearSearch(){
  const input=$('search');
  if(!input)return;

  input.value='';
  clearTimeout(searchDebounceTimer);
  updateSearchClear();
  clearTimeout(searchDebounceTimer);

  input.focus();
  await load();
}


function openHeaderSearch(){
  const topbar=$('appTopbar');
  const input=$('search');

  if(!topbar || !input)return;

  sidebarShowView('inventoryView',0);

  topbar.classList.add('search-open');
  document.body.classList.add('header-search-active');

  requestAnimationFrame(()=>{
    input.focus();
    input.select();
  });
}

async function closeHeaderSearch(){
  const topbar=$('appTopbar');
  const input=$('search');

  if(!topbar || !input)return;

  const hadValue=input.value.length>0;

  input.value='';
  clearTimeout(searchDebounceTimer);
  updateSearchClear();
  clearTimeout(searchDebounceTimer);
  topbar.classList.remove('search-open');
  document.body.classList.remove('header-search-active');

  if(hadValue){
    await load();
  }
}


function supportsSpeech(){
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

function attachVoiceButton(input){
  if(!input || input.dataset.voiceReady==='1') return;
  input.dataset.voiceReady='1';

  const wrap=document.createElement('div');
  wrap.className='voicewrap'+(input.tagName==='TEXTAREA'?' textarea':'');
  input.parentNode.insertBefore(wrap,input);
  wrap.appendChild(input);

  const btn=document.createElement('button');
  btn.type='button';
  btn.className='micbtn';
  btn.textContent='🎤';
  btn.title='Dettatura vocale';
  wrap.appendChild(btn);

  if(!supportsSpeech()){
    btn.disabled=true;
    btn.title='Dettatura vocale non supportata da questo browser';
    return;
  }

  btn.onclick=()=>{
    const SR=window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec=new SR();
    rec.lang='it-IT';
    rec.interimResults=false;
    rec.continuous=false;

    btn.classList.add('listening');
    btn.textContent='🔴';

    rec.onresult=(e)=>{
      const spoken=e.results?.[0]?.[0]?.transcript || '';
      if(!spoken) return;
      const start=input.selectionStart ?? input.value.length;
      const end=input.selectionEnd ?? input.value.length;
      const before=input.value.slice(0,start);
      const after=input.value.slice(end);
      const join=(before && !/\s$/.test(before))?' ':'';
      input.value=before+join+spoken+after;
      input.dispatchEvent(new Event('input',{bubbles:true}));
      input.focus();
    };
    rec.onerror=()=>{};
    rec.onend=()=>{
      btn.classList.remove('listening');
      btn.textContent='🎤';
    };
    rec.start();
  };
}

function enableVoiceInputs(scope=document){
  const selectors=[
    'input[type="text"]',
    'input:not([type])',
    'textarea'
  ];
  scope.querySelectorAll(selectors.join(',')).forEach(el=>{
    const allowedStatic=['aName','aDesc','aNotes','aTags','eName','eDesc','eNotes','eTags'];
    const isCustom=!!el.dataset.cfid;
    const isTypeEditor=!!el.closest('.fieldrow') && el.classList.contains('flabel');
    if(!(allowedStatic.includes(el.id) || isCustom || isTypeEditor)) return;
    if(el.closest('.fieldrow') && (el.classList.contains('fopts') || el.classList.contains('fplaceholder'))) return;
    attachVoiceButton(el);
  });
}

function currentItemsGrouping(){
  const saved=localStorage.getItem('inventario_items_group_by')||'type';
  return ['type','environment','none'].includes(saved)?saved:'type';
}

async function changeItemsGrouping(value){
  const grouping=['type','environment','none'].includes(value)?value:'type';
  localStorage.setItem('inventario_items_group_by',grouping);
  await loadInventoryGroups();
  renderInventory();
}

function groupStorageKey(grouping,key){
  return 'inventario_group_collapsed_'+grouping+'_'+String(key||'').toLowerCase();
}

function isGroupCollapsed(grouping,key){
  const saved=localStorage.getItem(groupStorageKey(grouping,key));
  // v2: i gruppi nuovi partono chiusi, così non carichiamo centinaia di righe inutilmente.
  return saved===null ? true : saved==='1';
}

async function toggleItemGroup(btn){
  const group=btn.closest('.item-group');
  if(!group)return;
  const grouping=group.dataset.grouping;
  const key=group.dataset.groupKey;
  const collapsed=group.classList.toggle('collapsed');
  localStorage.setItem(groupStorageKey(grouping,key),collapsed?'1':'0');
  if(!collapsed){
    await ensureOpenGroupLoaded(grouping,key);
    // Un rendering precedente puo aver svuotato il corpo del gruppo chiuso.
    renderInventory();
  }
}

function setNewItemCollapsed(collapsed){
  const panel=$('newItemPanel');
  const chevron=$('newItemChevron');
  if(!panel)return;
  panel.classList.toggle('collapsed',collapsed);
  const head=panel.querySelector('.new-item-head');
  if(head) head.setAttribute('aria-expanded',collapsed?'false':'true');
  if(chevron) chevron.textContent=collapsed?'▾':'▴';
}

function toggleNewItemPanel(){
  const panel=$('newItemPanel');
  if(!panel)return;
  setNewItemCollapsed(!panel.classList.contains('collapsed'));
}

async function loadInventoryGroups(){
  const q=$('search').value.trim();
  const grouping=currentItemsGrouping();
  const params=new URLSearchParams({
    group_by:grouping,
    page_size:String(getPageSize())
  });
  if(q)params.set('q',q);
  const data=await api('api/inventory-groups?'+params.toString());
  S.groups=data.groups||[];
  S.matched_count=Number(data.matched_count||0);
  S.page_size=getPageSize();
  S.groupItems={};
  S.groupHasMore={};
  S.groupOffsets={};
  S.subgroups={};
  S.subgroupItems={};
  S.subgroupHasMore={};
  S.subgroupOffsets={};
  S.items=[];
}

function mergeLoadedItems(items){
  const byId=new Map((S.items||[]).map(i=>[i.id,i]));
  for(const item of (items||[]))byId.set(item.id,item);
  S.items=[...byId.values()];
}

function rebuildVisibleItems(){
  const byId=new Map();

  for(const rows of Object.values(S.groupItems||{})){
    for(const item of (rows||[])) byId.set(item.id,item);
  }

  for(const rows of Object.values(S.subgroupItems||{})){
    for(const item of (rows||[])) byId.set(item.id,item);
  }

  S.items=[...byId.values()];
}

async function loadGroupPage(key,reset=false,requestedOffset=null){
  const grouping=currentItemsGrouping();
  const pageSize=S.page_size||50;
  const current=Number(S.groupOffsets?.[key]||0);

  const offset=requestedOffset===null
    ? (reset ? 0 : current+pageSize)
    : Math.max(0,Number(requestedOffset)||0);

  const q=$('search').value.trim();

  const params=new URLSearchParams({
    group_by:grouping,
    group_key:key,
    offset:String(offset)
  });

  if(q)params.set('q',q);

  const data=await api('api/inventory-items?'+params.toString());

  S.groupItems[key]=data.items||[];
  S.groupOffsets[key]=Number(data.offset??offset);
  S.groupHasMore[key]=!!data.has_more;

  rebuildVisibleItems();
  renderInventory();
}

async function loadMoreGroup(key,event){
  event?.stopPropagation?.();
  await loadGroupPage(key,false);
}

async function loadPreviousGroup(key,event){
  event?.stopPropagation?.();
  const pageSize=S.page_size||50;
  const current=Number(S.groupOffsets?.[key]||0);
  await loadGroupPage(key,false,Math.max(0,current-pageSize));
}

async function loadFirstGroup(key,event){
  event?.stopPropagation?.();
  await loadGroupPage(key,false,0);
}

async function loadLastGroup(key,total,event){
  event?.stopPropagation?.();
  const pageSize=S.page_size||50;
  const offset=Math.floor(Math.max(0,Number(total||0)-1)/pageSize)*pageSize;
  await loadGroupPage(key,false,offset);
}

async function load(){
  const q=$('search').value.trim();
  const params=new URLSearchParams();
  if(q)params.set('q',q);
  S=await api('api/bootstrap?'+params.toString());
  S.groups=[];
  S.groupItems={};
  S.groupHasMore={};
  S.groupOffsets={};
  S.subgroups={};
  S.subgroupItems={};
  S.subgroupHasMore={};
  S.subgroupOffsets={};
  S.items=[];
  S.page_size=getPageSize();
  await loadInventoryGroups();
  render();
}

function showTab(prefix,name,btn){
  document.querySelectorAll(`[id^="${prefix}-"]`).forEach(x=>x.classList.remove('active'));
  $(prefix+'-'+name).classList.add('active');
  btn.parentElement.querySelectorAll('.tabbtn').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
}

function typeById(id){return S.types.find(t=>String(t.id)===String(id));}
function dl(id,arr){$(id).innerHTML=(arr||[]).map(x=>`<option value="${esc(x)}">`).join('');}

function renderTypes(){
  const box=$('typeList');
  if(!box)return;
  const q=($('typeSearch')?.value||'').trim().toLowerCase();
  const rows=S.types.filter(typeDef=>!q || typeDef.name.toLowerCase().includes(q));
  box.innerHTML=rows.length ? rows.map(typeDef=>{
    const count=(typeDef.fields||[]).filter(f=>f.active).length;
    return `<div class="typecard" onclick="editType(${typeDef.id})" title="${esc(tf('open_type',{name:typeDef.name}))}">
      <div class="typecard-main">
        <span class="typeicon">${esc(typeDef.icon)}</span>
        <span class="typename">${esc(typeDef.name)}</span>
      </div>
      <span class="typecount">${count} ${count===1?t('field_count_one'):t('field_count_many')}</span>
    </div>`;
  }).join('') : `<div class="empty">${t('no_types_found')}</div>`;
}

function setTypePanelCollapsed(collapsed){
  const p=$('typePanel');
  const b=$('typeCollapseBtn');
  if(!p||!b)return;
  p.classList.toggle('collapsed',collapsed);
  b.textContent=collapsed?'▸':'▾';
  b.title=collapsed?t('expand_types'):t('collapse_types');
  localStorage.setItem('inventario_type_panel_collapsed',collapsed?'1':'0');
}
function toggleTypePanel(){
  setTypePanelCollapsed(!$('typePanel').classList.contains('collapsed'));
}

function render(){
  $('countItems').textContent=S.counts.items;
  $('countEnv').textContent=S.counts.environments;
  $('countTypes').textContent=S.counts.types;

  const grouping=currentItemsGrouping();
  if($('itemsGroupBy')) $('itemsGroupBy').value=grouping;
  const matched=Number(S.matched_count||0);
  if($('itemsListInfo')){
    $('itemsListInfo').textContent=matched ? tf(matched===1?'items_total_one':'items_total_many',{count:matched}) : '';
  }

  const typeOpts=S.types.map(t=>`<option value="${t.id}">${esc(t.icon)} ${esc(t.name)}</option>`).join('');
  $('aType').innerHTML=typeOpts;
  $('eType').innerHTML=typeOpts;

  dl('envs',S.suggestions.environment);
  dl('furns',S.suggestions.furniture);
  dl('shelves',S.suggestions.shelf);
  dl('containers',S.suggestions.container);

  renderCustom('add');
  enableVoiceInputs(document);

  renderTypes();

  renderInventory();

  $('itemsTitle').textContent=$('search').value.trim()?t('inventory_results'):t('inventory_owned');
}


function renderItemRow(i){
  return `<button type="button" class="item item-row" onclick="showItemPreview(${i.id})" aria-label="${esc(tf('open_item',{name:i.name}))}">
    <span class="itemname">${esc(i.type_icon||'📦')} ${esc(i.name)}${i.quantity>1?' × '+i.quantity:''}</span>
    <span class="item-chevron">›</span>
  </button>`;
}

function renderLoadMore(key,loaded,total){
  if(!loaded)return '';

  const offset=Number(S.groupOffsets?.[key]||0);
  const first=offset+1;
  const last=Math.min(offset+loaded,total);

  const hasPrev=offset>0;
  const hasNext=!!S.groupHasMore[key];

  return `<div class="inventory-pager">
    ${hasPrev ? `
      <button type="button" class="secondary" onclick="loadFirstGroup('${esc(key)}',event)">⏮ ${t('first')}</button>
      <button type="button" class="secondary" onclick="loadPreviousGroup('${esc(key)}',event)">‹ ${t('previous')}</button>
    ` : ''}

    <span class="hint"><strong>${tf('range_of_total',{first,last,total})}</strong></span>

    ${hasNext ? `
      <button type="button" class="secondary" onclick="loadMoreGroup('${esc(key)}',event)">${t('next')} ›</button>
      <button type="button" class="secondary" onclick="loadLastGroup('${esc(key)}',${total},event)">${t('last')} ⏭</button>
    ` : ''}
  </div>`;
}

function subgroupCacheKey(typeKey,subKey){return String(typeKey)+'::'+String(subKey);}
function subgroupStorageKey(typeKey,subKey){return 'inventario_subgroup_collapsed_'+typeKey+'_'+String(subKey).toLowerCase();}
function isSubgroupCollapsed(typeKey,subKey){const v=localStorage.getItem(subgroupStorageKey(typeKey,subKey));return v===null?true:v==='1';}
async function loadSubgroups(typeKey){
  // undefined = non ancora verificato; null = verificato, sottogruppi disabilitati.
  if(S.subgroups[typeKey] !== undefined)return;
  const q=$('search').value.trim(); const p=new URLSearchParams({type_id:String(typeKey)}); if(q)p.set('q',q);
  const d=await api('api/inventory-subgroups?'+p.toString());
  S.subgroups[typeKey]=d.enabled?(d.subgroups||[]):null;
  renderInventory();
}

async function ensureOpenGroupLoaded(grouping,key){
  S.openGroupLoads=S.openGroupLoads||{};
  const loadKey=grouping+'::'+String(key);
  if(S.openGroupLoads[loadKey])return S.openGroupLoads[loadKey];

  const job=(async()=>{
    if(grouping==='type'){
      await loadSubgroups(key);
      if(S.subgroups[key]===null && !(S.groupItems[key]||[]).length){
        await loadGroupPage(key,true);
      }
    }else if(!(S.groupItems[key]||[]).length){
      await loadGroupPage(key,true);
    }
  })();

  S.openGroupLoads[loadKey]=job;
  try{
    await job;
  }finally{
    delete S.openGroupLoads[loadKey];
  }
}
async function toggleSubgroup(btn){
  const el=btn.closest('.item-subgroup'); if(!el)return;
  const tk=el.dataset.typeKey, sk=el.dataset.subgroupKey, collapsed=el.classList.toggle('collapsed');
  localStorage.setItem(subgroupStorageKey(tk,sk),collapsed?'1':'0');
  const ck=subgroupCacheKey(tk,sk);
  if(!collapsed && !(S.subgroupItems[ck]||[]).length) await loadSubgroupPage(tk,sk,true);
}
async function loadSubgroupPage(typeKey,subKey,reset=false,requestedOffset=null){
  const ck=subgroupCacheKey(typeKey,subKey);
  const pageSize=S.page_size||50;
  const current=Number(S.subgroupOffsets?.[ck]||0);

  const offset=requestedOffset===null
    ? (reset ? 0 : current+pageSize)
    : Math.max(0,Number(requestedOffset)||0);

  const q=$('search').value.trim();

  const p=new URLSearchParams({
    type_id:String(typeKey),
    subgroup_key:String(subKey),
    offset:String(offset)
  });

  if(q)p.set('q',q);

  const d=await api('api/inventory-subgroup-items?'+p.toString());

  S.subgroupItems[ck]=d.items||[];
  S.subgroupOffsets[ck]=Number(d.offset??offset);
  S.subgroupHasMore[ck]=!!d.has_more;

  rebuildVisibleItems();
  renderInventory();
}

async function loadMoreSubgroup(typeKey,subKey,event){
  event?.stopPropagation?.();
  await loadSubgroupPage(typeKey,subKey,false);
}

async function loadPreviousSubgroup(typeKey,subKey,event){
  event?.stopPropagation?.();

  const ck=subgroupCacheKey(typeKey,subKey);
  const pageSize=S.page_size||50;
  const current=Number(S.subgroupOffsets?.[ck]||0);

  await loadSubgroupPage(
    typeKey,
    subKey,
    false,
    Math.max(0,current-pageSize)
  );
}

async function loadFirstSubgroup(typeKey,subKey,event){
  event?.stopPropagation?.();
  await loadSubgroupPage(typeKey,subKey,false,0);
}

async function loadLastSubgroup(typeKey,subKey,total,event){
  event?.stopPropagation?.();

  const pageSize=S.page_size||50;
  const offset=Math.floor(
    Math.max(0,Number(total||0)-1)/pageSize
  )*pageSize;

  await loadSubgroupPage(typeKey,subKey,false,offset);
}

function renderSubgroupLoadMore(typeKey,subKey,loaded,total){
  if(!loaded)return '';

  const ck=subgroupCacheKey(typeKey,subKey);
  const offset=Number(S.subgroupOffsets?.[ck]||0);

  const first=offset+1;
  const last=Math.min(offset+loaded,total);

  const hasPrev=offset>0;
  const hasNext=!!S.subgroupHasMore[ck];

  return `<div class="inventory-pager">
    ${hasPrev ? `
      <button type="button" class="secondary" onclick="loadFirstSubgroup('${esc(typeKey)}','${esc(subKey)}',event)">⏮ ${t('first')}</button>
      <button type="button" class="secondary" onclick="loadPreviousSubgroup('${esc(typeKey)}','${esc(subKey)}',event)">‹ ${t('previous')}</button>
    ` : ''}

    <span class="hint"><strong>${tf('range_of_total',{first,last,total})}</strong></span>

    ${hasNext ? `
      <button type="button" class="secondary" onclick="loadMoreSubgroup('${esc(typeKey)}','${esc(subKey)}',event)">${t('next')} ›</button>
      <button type="button" class="secondary" onclick="loadLastSubgroup('${esc(typeKey)}','${esc(subKey)}',${total},event)">${t('last')} ⏭</button>
    ` : ''}
  </div>`;
}

function renderTypeSubgroups(typeKey){
  const subs=S.subgroups[typeKey];
  if(subs===undefined){setTimeout(()=>loadSubgroups(typeKey),0);return `<div class="inventory-loader">${t('loading_subgroups')}</div>`;}
  if(subs===null)return null;
  if(!subs.length)return `<div class="empty">${t('no_items')}</div>`;
  return subs.map(g=>{const sk=String(g.subgroup_key),ck=subgroupCacheKey(typeKey,sk),items=S.subgroupItems[ck]||[],total=Number(g.item_count||0),collapsed=isSubgroupCollapsed(typeKey,sk);
    const body=items.length?items.map(renderItemRow).join('')+renderSubgroupLoadMore(typeKey,sk,items.length,total):`<div class="inventory-loader">${t('open_subgroup_load')}</div>`;
    if(!collapsed && !items.length)setTimeout(()=>loadSubgroupPage(typeKey,sk,true),0);
    return `<section class="item-subgroup${collapsed?' collapsed':''}" data-type-key="${esc(typeKey)}" data-subgroup-key="${esc(sk)}"><button type="button" class="item-subgroup-head" onclick="toggleSubgroup(this)"><span class="item-subgroup-title">↳ ${esc(g.label)}</span><span class="item-group-side"><span class="item-group-count">${total}</span><span class="item-subgroup-arrow">⌄</span></span></button><div class="item-subgroup-body">${body}</div></section>`;
  }).join('');
}

function renderInventory(){
  const box=$('items');
  if(!box)return;
  const grouping=currentItemsGrouping();
  const groups=S.groups||[];

  if(!groups.length){
    box.innerHTML=`<div class="empty">${t('no_items')}</div>`;
    return;
  }

  if(grouping==='none'){
    const g=groups[0];
    const key=String(g.group_key||'all');
    const items=S.groupItems[key]||[];
    box.innerHTML=`
      <div class="flat-items-body">
        ${items.length?items.map(renderItemRow).join(''):`<div class="inventory-loader">${t('loading_items')}</div>`}
        ${renderLoadMore(key,items.length,Number(g.item_count||0))}
      </div>`;
    if(!items.length)loadGroupPage(key,true);
    return;
  }

  box.innerHTML=groups.map(g=>{
    const key=String(g.group_key);
    const collapsed=isGroupCollapsed(grouping,key);
    const items=S.groupItems[key]||[];
    const total=Number(g.item_count||0);
    let body;
    if(grouping==='type'){
      // I gruppi chiusi non devono avviare richieste di sottogruppi.
      const subhtml=collapsed ? undefined : renderTypeSubgroups(key);
      if(collapsed) body='';
      else if(subhtml!==null) body=subhtml;
      else body=items.length ? `${items.map(renderItemRow).join('')}${renderLoadMore(key,items.length,total)}` : `<div class="inventory-loader">${t('loading_items')}</div>`;
    }else{
      body=items.length ? `${items.map(renderItemRow).join('')}${renderLoadMore(key,items.length,total)}` : `<div class="inventory-loader">${t('open_group_load')}</div>`;
    }
    return `
      <section class="item-group${collapsed?' collapsed':''}" data-grouping="${grouping}" data-group-key="${esc(key)}">
        <button type="button" class="item-group-head" onclick="toggleItemGroup(this)">
          <span class="item-group-title"><span>${esc(g.icon||'📦')}</span><span>${esc(g.label||t('group'))}</span></span>
          <span class="item-group-side">
            <span class="item-group-count">${total}</span>
            <span class="item-group-arrow">⌄</span>
          </span>
        </button>
        <div class="item-group-body">${body}</div>
      </section>`;
  }).join('');

  // Carica soltanto i gruppi realmente aperti. La stessa routine gestisce
  // tipologie con sottogruppi e tipologie semplici senza creare richieste duplicate.
  for(const g of groups){
    const key=String(g.group_key);
    if(!isGroupCollapsed(grouping,key)) ensureOpenGroupLoaded(grouping,key);
  }
}

function renderCustom(mode,values={}){
  const typeId=$(mode==='add'?'aType':'eType').value;
  const typeDef=typeById(typeId);
  const box=$(mode==='add'?'customAdd':'customEdit');
  if(!typeDef){box.innerHTML=`<div class="empty">${window.t('no_fields')}</div>`;return;}

  const fields=(typeDef.fields||[]).filter(f=>f.active);
  if(!fields.length){box.innerHTML=`<div class="empty">${window.t('no_custom_fields')}</div>`;return;}

  box.innerHTML=fields.map(f=>{
    const v=values[String(f.id)]??'';
    const req=f.required?' *':'';
    const ph=esc(f.placeholder||'');
    let control='';

    if(f.field_type==='textarea'){
      control=`<textarea data-cfid="${f.id}" placeholder="${ph}">${esc(v)}</textarea>`;
    }else if(f.field_type==='select'){
      const opts=(f.options||'').split(',').map(x=>x.trim()).filter(Boolean);
      control=`<select data-cfid="${f.id}"><option value=""></option>${opts.map(o=>`<option value="${esc(o)}"${String(v)===o?' selected':''}>${esc(o)}</option>`).join('')}</select>${ph?`<span class="hint">${ph}</span>`:''}`;
    }else if(f.field_type==='checkbox'){
      control=`<select data-cfid="${f.id}"><option value=""></option><option value="1"${String(v)==='1'?' selected':''}>${window.t('yes')}</option><option value="0"${String(v)==='0'?' selected':''}>${window.t('no')}</option></select>`;
    }else{
      const typ=f.field_type==='number'?'number':f.field_type==='date'?'date':'text';
      control=`<input type="${typ}" data-cfid="${f.id}" value="${esc(v)}" placeholder="${ph}">`;
    }

    const filled=String(v).trim()!=='' ? '<span class="custom-field-filled">✓</span>' : '';
    const normalizedLabel=String(f.label||'').toLowerCase().replace(/\s+/g,' ').trim();
    const isBookCode=normalizedLabel==='isbn' || normalizedLabel==='isbn / ean' || normalizedLabel==='isbn/ean';
    const lookup=isBookCode ? `
      <div class="book-lookup-row">
        <button type="button" class="secondary small scan-code-btn" onclick="startBarcodeScan('${mode}',${f.id},this)">${window.t('scan_code')}</button>
        <button type="button" class="secondary small" onclick="lookupBookData('${mode}',${f.id},this)">${window.t('search_data')}</button>
        <span class="book-lookup-status"></span>
      </div>` : '';
    return `
      <div class="custom-field-accordion">
        <button type="button" class="custom-field-title" onclick="toggleCustomField(this)">
          <span>${esc(f.label)+req}</span>
          <span class="custom-field-title-right">${filled}<span class="custom-field-arrow">⌄</span></span>
        </button>
        <div class="custom-field-body">
          ${control}
          ${lookup}
        </div>
      </div>`;
  }).join('');

  enableVoiceInputs(box);
  updateCameraAvailability();
}

function updatePhotoFileName(input){
  const label=$('photoFileName');
  if(!label)return;

  if(input?.files?.length){
    label.removeAttribute('data-i18n');
    label.textContent=input.files[0].name;
  }else{
    label.dataset.i18n='no_file_selected';
    label.textContent=t('no_file_selected');
  }
}

function toggleCustomField(btn){
  const row=btn.closest('.custom-field-accordion');
  if(!row)return;
  const box=row.parentElement;
  const already=row.classList.contains('open');

  box.querySelectorAll('.custom-field-accordion.open').forEach(x=>{
    if(x!==row)x.classList.remove('open');
  });

  row.classList.toggle('open',!already);

  if(!already){
    const el=row.querySelector('input,select,textarea');
    if(el)setTimeout(()=>el.focus(),60);
  }
}


function findCustomInputByLabel(mode,labelNames){
  const typeId=$(mode==='add'?'aType':'eType').value;
  const typeDef=typeById(typeId);
  if(!typeDef)return null;
  const wanted=labelNames.map(x=>x.toLowerCase());
  const f=(typeDef.fields||[]).find(x=>wanted.includes(String(x.label||'').toLowerCase()));
  if(!f)return null;
  return document.querySelector(`#${mode==='add'?'customAdd':'customEdit'} [data-cfid="${f.id}"]`);
}

function setIfEmpty(el,value){
  if(!el || !value || String(el.value||'').trim()!=='')return false;
  el.value=value;
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return true;
}


let barcodeStream=null;
let barcodeDetector=null;
let barcodeScanTimer=null;
let barcodeTarget=null;
let barcodeBusy=false;
let barcodeFallbackMode=false;

function cameraSecureContextAvailable(){
  return !!(window.isSecureContext &&
            navigator.mediaDevices?.getUserMedia);
}

function updateCameraAvailability(){
  const available=cameraSecureContextAvailable();

  document.querySelectorAll('.scan-code-btn').forEach(btn=>{
    btn.disabled=!available;
    btn.title=available
      ? t('scan_code_camera')
      : t('camera_https_required');
  });
}

function normalizeBarcodeValue(raw){
  return String(raw||'').trim().replace(/[^0-9Xx]/g,'').toUpperCase();
}

function barcodeValueLooksUseful(code){
  return [8,10,12,13].includes(code.length);
}

async function makeBarcodeDetector(){
  if(!('BarcodeDetector' in window))return null;
  let formats=['ean_13','ean_8','upc_a','upc_e','code_128'];
  try{
    if(typeof BarcodeDetector.getSupportedFormats==='function'){
      const supported=await BarcodeDetector.getSupportedFormats();
      const filtered=formats.filter(x=>supported.includes(x));
      if(filtered.length)formats=filtered;
    }
    return new BarcodeDetector({formats});
  }catch(e){
    return null;
  }
}

function applyScannedBarcode(raw){
  if(!barcodeTarget)return false;
  const code=normalizeBarcodeValue(raw);
  if(!barcodeValueLooksUseful(code))return false;
  const {mode,fieldId}=barcodeTarget;
  const box=$(mode==='add'?'customAdd':'customEdit');
  const input=box?.querySelector(`[data-cfid="${fieldId}"]`);
  if(!input)return false;
  input.value=code;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.dispatchEvent(new Event('change',{bubbles:true}));
  const status=barcodeTarget.statusEl;
  if(status)status.textContent=tf('code_detected',{code});
  stopBarcodeScan(false);
  return true;
}

async function decodeBarcodeOnServer(blob, filename='frame.jpg'){
  const fd=new FormData();
  fd.append('image',blob,filename);
  const resp=await fetch('api/decode-barcode',{method:'POST',body:fd});
  let data={};
  try{data=await resp.json();}catch(e){}
  if(!resp.ok)throw new Error(data.error||t('barcode_read_error'));
  for(const b of (data.barcodes||[])){
    if(applyScannedBarcode(b.code||b.raw))return true;
  }
  return false;
}

async function startBarcodeScan(mode,fieldId,btn){
  barcodeTarget={mode,fieldId,statusEl:btn.parentElement.querySelector('.book-lookup-status')};

  // v2.3.5 - la fotocamera viene usata solo in un contesto sicuro.
  // In HTTP l'inserimento manuale e il caricamento di file restano disponibili.
  const canLiveCamera=cameraSecureContextAvailable();
  if(!canLiveCamera){
    const targetStatus=barcodeTarget.statusEl;
    if(targetStatus){
      targetStatus.textContent=t('camera_https_manual');
    }
    barcodeTarget=null;
    return;
  }

  const dlg=$('barcodeDlg'), video=$('barcodeVideo'), status=$('barcodeStatus');
  dlg.classList.add('show');
  status.textContent=t('camera_starting');
  try{
    barcodeDetector=await makeBarcodeDetector();
    barcodeFallbackMode=!barcodeDetector;
    barcodeStream=await navigator.mediaDevices.getUserMedia({
      video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false
    });
    video.srcObject=barcodeStream;
    await video.play();
    status.textContent=barcodeFallbackMode
      ? t('camera_frame_fallback')
      : t('camera_frame');
    barcodeScanLoop();
  }catch(e){
    // Se il browser espone getUserMedia ma poi lo blocca (Ingress/WebView,
    // permessi o policy), manteniamo il fallback foto sempre disponibile.
    status.textContent=t('camera_live_unavailable');
    const photoBtn=$('barcodePhotoBtn');
    if(photoBtn) photoBtn.focus();
  }
}

async function decodeCurrentVideoFrame(){
  const video=$('barcodeVideo');
  if(!video || video.readyState<2 || !video.videoWidth || !video.videoHeight)return false;
  const maxW=960;
  const scale=Math.min(1,maxW/video.videoWidth);
  const canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(video.videoWidth*scale));
  canvas.height=Math.max(1,Math.round(video.videoHeight*scale));
  const ctx=canvas.getContext('2d',{alpha:false});
  ctx.drawImage(video,0,0,canvas.width,canvas.height);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.72));
  if(!blob)return false;
  return decodeBarcodeOnServer(blob,'camera.jpg');
}

async function barcodeScanLoop(){
  if(!barcodeStream)return;
  const video=$('barcodeVideo');
  if(!barcodeBusy && video.readyState>=2){
    barcodeBusy=true;
    try{
      if(barcodeDetector){
        const found=await barcodeDetector.detect(video);
        if(found?.length){
          for(const b of found){if(applyScannedBarcode(b.rawValue))return;}
        }
      }else{
        if(await decodeCurrentVideoFrame())return;
      }
    }catch(e){}
    finally{barcodeBusy=false;}
  }
  barcodeScanTimer=setTimeout(barcodeScanLoop,barcodeDetector?180:500);
}

function stopBarcodeScan(clearTarget=true){
  if(barcodeScanTimer){clearTimeout(barcodeScanTimer);barcodeScanTimer=null;}
  if(barcodeStream){barcodeStream.getTracks().forEach(t=>t.stop());barcodeStream=null;}
  const video=$('barcodeVideo');
  if(video){video.pause();video.srcObject=null;}
  $('barcodeDlg')?.classList.remove('show');
  barcodeBusy=false;
  barcodeFallbackMode=false;
  if(clearTarget)barcodeTarget=null;
}

function chooseBarcodePhoto(){
  if(!cameraSecureContextAvailable()){
    const status=$('barcodeStatus');
    if(status){
      status.textContent=t('camera_https');
    }
    return;
  }

  if(barcodeStream){barcodeStream.getTracks().forEach(t=>t.stop());barcodeStream=null;}
  const inp=$('barcodePhotoInput');
  if(inp){inp.value='';inp.click();}
}

async function scanBarcodePhoto(input){
  const status=$('barcodeStatus');
  const targetStatus=barcodeTarget?.statusEl;
  const file=input.files?.[0];
  if(!file){
    if(targetStatus) targetStatus.textContent=t('scan_cancelled');
    return;
  }
  if(!$('barcodeDlg').classList.contains('show')) $('barcodeDlg').classList.add('show');
  status.textContent=t('analysing_code_photo');
  try{
    const detector=await makeBarcodeDetector();
    if(detector && 'createImageBitmap' in window){
      try{
        const bitmap=await createImageBitmap(file);
        const found=await detector.detect(bitmap);
        bitmap.close?.();
        for(const b of (found||[])){if(applyScannedBarcode(b.rawValue))return;}
      }catch(e){}
    }
    if(await decodeBarcodeOnServer(file,file.name||'barcode.jpg'))return;
    status.textContent=t('code_not_found_photo');
  }catch(e){
    status.textContent=e.message||t('code_photo_error');
  }
}

async function lookupBookData(mode,fieldId,btn){
  const box=$(mode==='add'?'customAdd':'customEdit');
  const codeEl=box.querySelector(`[data-cfid="${fieldId}"]`);
  const status=btn.parentElement.querySelector('.book-lookup-status');
  const code=(codeEl?.value||'').trim();
  if(!code){alert(t('enter_code_first'));codeEl?.focus();return;}

  const oldText=btn.textContent;
  btn.disabled=true;
  btn.textContent=t('searching');
  status.textContent='';
  try{
    const data=await api('api/lookup-book?code='+encodeURIComponent(code));
    const lines=[];
    if(data.title)lines.push('Titolo: '+data.title);
    if((data.authors||[]).length)lines.push('Autore: '+data.authors.join(', '));
    if(data.publisher)lines.push('Editore: '+data.publisher);
    if(data.publish_date)lines.push('Data: '+data.publish_date);
    if(data.year)lines.push('Anno: '+data.year);
    lines.push('Codice: '+data.code);

    const ok=confirm(tf('data_found_confirm',{source:data.source,lines:lines.join('\n')}));
    if(!ok){status.textContent=t('data_not_applied');return;}

    let applied=0;
    const nameEl=$(mode==='add'?'aName':'eName');
    if(setIfEmpty(nameEl,data.title))applied++;
    if(setIfEmpty(findCustomInputByLabel(mode,['Autore']), (data.authors||[]).join(', ')))applied++;
    if(setIfEmpty(findCustomInputByLabel(mode,['Editore']),data.publisher))applied++;
    if(setIfEmpty(findCustomInputByLabel(mode,['Anno']),data.year))applied++;
    if(setIfEmpty(codeEl,data.code))applied++;

    status.textContent=applied ? tf('fields_filled',{count:applied}) : t('no_empty_fields');
  }catch(e){
    alert(e.message);
    status.textContent=t('search_failed');
  }finally{
    btn.disabled=false;
    btn.textContent=oldText;
  }
}


function collectCustom(boxId){
  const out={};
  document.querySelectorAll('#'+boxId+' [data-cfid]').forEach(el=>out[String(el.dataset.cfid)]=el.value);
  return out;
}

async function createItem(){
  try{
    const data=await api('api/items',{method:'POST',body:JSON.stringify({
      name:$('aName').value,
      item_type_id:$('aType').value||null,
      quantity:$('aQty').value,
      environment:$('aEnv').value,
      environment_id:$('aEnv').selectedOptions[0]?.dataset.environmentId || null,
      furniture:$('aFurn').value,
      shelf:$('aShelf').value,
      container_name:$('aCont').value,
      container_code:$('aCode').value,
      description:$('aDesc').value,
      notes:$('aNotes').value,
      tags:$('aTags').value,
      custom_values:collectCustom('customAdd')
    })});
    ['aName','aEnv','aFurn','aShelf','aCont','aCode','aDesc','aNotes','aTags'].forEach(id=>$(id).value='');
    $('aQty').value=1;
    await load();
  setNewItemCollapsed(true);
    editItem(data.id);
    const photoBtn=document.querySelector('#editDlg .tabbtn[data-tab="photos"]');
    if(photoBtn) photoBtn.click();
  }catch(e){alert(e.message);}
}

function addPreviewRow(rows,label,value){
  if(value===null || value===undefined || String(value).trim()==='') return;
  rows.push(`<div class="item-preview-row"><div class="item-preview-label">${esc(label)}</div><div class="item-preview-value">${esc(value)}</div></div>`);
}

async function showItemPreview(id){
  let i;
  try{
    i=await api('api/items/'+id);
    mergeLoadedItems([i]);
  }catch(e){
    alert(e.message);
    return;
  }
  const topbar=$('appTopbar');
  const searchInput=$('search');

  if(searchInput){
    searchInput.value='';
    clearTimeout(searchDebounceTimer);
    updateSearchClear();
    clearTimeout(searchDebounceTimer);
  }

  if(topbar){
    topbar.classList.remove('search-open');
  }

  document.body.classList.remove('header-search-active');

  viewingItem=id;
  const typeDef=typeById(i.item_type_id);
  const rows=[];
  addPreviewRow(rows,t('item_type'),`${typeDef?.icon||i.type_icon||'📦'} ${typeDef?.name||''}`.trim());
  if(Number(i.quantity||1)>1) addPreviewRow(rows,t('quantity'),i.quantity);
  const values=i.custom_values||{};
  for(const f of (typeDef?.fields||[])){
    if(!f.active) continue;
    const v=values[String(f.id)] ?? values[f.id];
    addPreviewRow(rows,f.label,v);
  }
  if(!locationsData.length) await loadLocations();

  let itemPropertyName = '';
  if(i.environment_id){
    const itemProperty = locationsData.find(prop =>
      (prop.environments || []).some(
        env => env.id === Number(i.environment_id)
      )
    );
    itemPropertyName = itemProperty?.name || '';
  }

  addPreviewRow(rows,t('property'),itemPropertyName);
  addPreviewRow(rows,t('environment'),i.environment);
  addPreviewRow(rows,t('furniture'),i.furniture);
  addPreviewRow(rows,t('shelf'),i.shelf);
  addPreviewRow(rows,t('container'),i.container_name);
  addPreviewRow(rows,t('container_code'),i.container_code);
  addPreviewRow(rows,t('description'),i.description);
  addPreviewRow(rows,t('tags'),i.tags);
  addPreviewRow(rows,t('notes'),i.notes);
  $('viewTitle').textContent=`${i.type_icon||typeDef?.icon||'📦'} ${i.name||t('item_details')}`;
  const photos=i.photos||[];
  if(photos.length){
    const visible=photos.slice(0,3);
    $('viewPhotos').innerHTML=`<div class="item-preview-photo-title">📷 ${t('photos')}</div>
      <div class="item-preview-photo-grid">${visible.map(p=>`
        <div class="item-preview-photo">
          <button type="button" onclick="openPhoto('${p.filename}')" aria-label="${esc(t('open_photo'))}">
            <img src="files/${encodeURIComponent(p.thumb_filename)}" alt="${esc(p.label||i.name||t('item_photo'))}">
          </button>
          ${p.label?`<div class="item-preview-photo-label">${esc(p.label)}</div>`:''}
        </div>`).join('')}</div>
      ${photos.length>3?`<div class="item-preview-photo-more">${tf('more_photos',{count:photos.length-3})}</div>`:''}`;
  }else{
    $('viewPhotos').innerHTML=`<button type="button" class="item-preview-no-photo" onclick="openPreviewPhotosEditor()">${t('no_photo_add')}</button>`;
  }
  $('viewDetails').innerHTML=rows.length?rows.join(''):`<div class="empty">${t('no_additional_details')}</div>`;
  $('viewDlg').classList.add('show');
}
function closeItemPreview(){$('viewDlg').classList.remove('show');viewingItem=null;}
function modifyPreviewItem(){const id=viewingItem;if(!id)return;closeItemPreview();editItem(id);}
async function openPreviewPhotosEditor(){
  const id=viewingItem;if(!id)return;
  closeItemPreview();
  await editItem(id);
  const photoBtn=document.querySelector('#editDlg .tabbtn[data-tab="photos"]');
  if(photoBtn) photoBtn.click();
}

async function editItem(id){
  let i=S.items.find(x=>x.id===id);
  if(!i){
    try{
      i=await api('api/items/'+id);
      mergeLoadedItems([i]);
    }catch(e){alert(e.message);return;}
  }
  editingItem=id;
  $('eName').value=i.name||'';
  $('eType').value=i.item_type_id||'';
  $('eQty').value=i.quantity||1;
  await loadEditLocations(i.environment || '', i.environment_id || null);
  $('eFurn').value=i.furniture||'';
  $('eShelf').value=i.shelf||'';
  $('eCont').value=i.container_name||'';
  $('eCode').value=i.container_code||'';
  $('eDesc').value=i.description||'';
  $('eNotes').value=i.notes||'';
  $('eTags').value=i.tags||'';
  $('photoProfile').value='auto';
  $('photoFile').value='';
  $('photoLabel').value='';
  renderCustom('edit',i.custom_values||{});
  renderPhotos(i);
  document.querySelectorAll('#editDlg .tab').forEach(x=>x.classList.remove('active'));
  $('edit-general').classList.add('active');
  document.querySelectorAll('#editDlg .tabbtn').forEach(x=>x.classList.remove('active'));
  document.querySelector('#editDlg .tabbtn').classList.add('active');
  $('editDlg').classList.add('show');
  enableVoiceInputs($('editDlg'));
}

function closeEdit(){$('editDlg').classList.remove('show');editingItem=null;}

async function saveItem(){
  if(!editingItem)return;
  try{
    await api('api/items/'+editingItem,{method:'PUT',body:JSON.stringify({
      name:$('eName').value,
      item_type_id:$('eType').value||null,
      quantity:$('eQty').value,
      environment:$('eEnv').value,
      environment_id:$('eEnv').selectedOptions[0]?.dataset.environmentId || null,
      furniture:$('eFurn').value,
      shelf:$('eShelf').value,
      container_name:$('eCont').value,
      container_code:$('eCode').value,
      description:$('eDesc').value,
      notes:$('eNotes').value,
      tags:$('eTags').value,
      custom_values:collectCustom('customEdit')
    })});
    await load();
    closeEdit();
  }catch(e){alert(e.message);}
}

async function deleteItem(id){
  if(!confirm(t('delete_item_confirm')))return;
  try{await api('api/items/'+id,{method:'DELETE'});await load();}catch(e){alert(e.message);}
}

async function deleteEditingItem(){
  if(!editingItem)return;
  const id=editingItem;
  const item=S.items.find(x=>x.id===id);
  const confirmMessage=item?.name
    ? tf('delete_item_named_confirm',{name:item.name})
    : t('delete_item_unnamed_confirm');
  if(!confirm(confirmMessage))return;
  try{
    await api('api/items/'+id,{method:'DELETE'});
    closeEdit();
    await load();
  }catch(e){alert(e.message);}
}

function renderPhotos(i){
  const photos=i.photos||[];
  $('photoGrid').innerHTML=photos.length?photos.map(p=>`
    <div class="photo">
      <img src="files/${encodeURIComponent(p.thumb_filename)}" onclick="openPhoto('${p.filename}')">
      <div class="meta">${esc(p.label||'')}</div>
      <button class="danger small" onclick="deletePhoto(${p.id})">${t('delete')}</button>
    </div>`).join(''):`<div class="empty">${t('no_photos')}</div>`;
}

function openPhoto(filename){
  const box=$('photoLightbox');
  const img=$('photoLightboxImg');
  img.src='files/'+encodeURIComponent(filename);
  box.classList.add('open');
  document.body.style.overflow='hidden';
}
function closePhoto(){
  const box=$('photoLightbox');
  const img=$('photoLightboxImg');
  box.classList.remove('open');
  img.removeAttribute('src');
  document.body.style.overflow='';
}
document.addEventListener('keydown',e=>{
  if(e.key==='Escape' && $('photoLightbox')?.classList.contains('open')) closePhoto();
});

async function uploadPhoto(){
  if(!editingItem)return;
  const file=$('photoFile').files[0];
  if(!file){alert(t('choose_photo'));return;}
  const fd=new FormData();
  fd.append('file',file);
  fd.append('profile',$('photoProfile').value);
  fd.append('label',$('photoLabel').value);
  const r=await fetch('api/items/'+editingItem+'/photos',{method:'POST',body:fd});
  const d=await r.json().catch(()=>({}));
  if(!r.ok){alert(d.error||t('photo_upload_error'));return;}
  // Ricarica subito l'elemento dal server per mostrare
  // anche la thumbnail della foto appena caricata.
  const item=await api('api/items/'+editingItem);
  mergeLoadedItems([item]);
  renderPhotos(item);

  $('photoFile').value='';
  $('photoLabel').value='';
  updatePhotoFileName($('photoFile'));
}

async function deletePhoto(id){
  if(!confirm(t('delete_photo_confirm')))return;
  try{
    await api('api/photos/'+id,{method:'DELETE'});

    // Ricarica solo l'elemento modificato e aggiorna subito
    // la galleria dopo l'eliminazione della foto.
    const item=await api('api/items/'+editingItem);
    mergeLoadedItems([item]);
    renderPhotos(item);
  }catch(e){alert(e.message);}
}

function refreshSubgroupFieldOptions(selected=''){
  const sel=$('tSubgroupField'); if(!sel)return;
  const rows=[...document.querySelectorAll('#typeFields .fieldrow')].filter(r=>r.dataset.active!=='0' && r.dataset.id);
  sel.innerHTML=`<option value="">${t('none')}</option>`+rows.map(r=>`<option value="${esc(r.dataset.id)}">${esc(r.querySelector('.flabel').value||t('field'))}</option>`).join('');
  sel.value=String(selected||'');
}

function openTypeDialog(){
  editingType=null;
  $('deleteTypeBtn').style.display='none';
  $('typeDlgTitle').textContent=t('new_type');
  $('tName').value='';
  $('tIconCustom').value='';
  $('tIcon').value='📦';
  $('typeFields').innerHTML='';
  addFieldRow();
  refreshSubgroupFieldOptions('');
  $('typeDlg').classList.add('show');
  enableVoiceInputs($('typeDlg'));
  enableVoiceInputs($('typeDlg'));
}

function closeTypeDialog(){$('typeDlg').classList.remove('show');editingType=null;}

function addFieldRow(field={}){
  const row=document.createElement('div');
  row.className='fieldrow'+(field.active===0?' inactive':'');
  row.dataset.id=field.id||'';
  row.dataset.active=field.active===0?'0':'1';
  row.innerHTML=`
    <input class="flabel" placeholder="${esc(t('field_name'))}" value="${esc(field.label||'')}">
    <select class="ftype">
      <option value="text">${t('field_text')}</option>
      <option value="number">${t('field_number')}</option>
      <option value="date">${t('field_date')}</option>
      <option value="textarea">${t('field_long_text')}</option>
      <option value="select">${t('field_list')}</option>
      <option value="checkbox">${t('field_yes_no')}</option>
    </select>
    <label class="check"><input class="freq" type="checkbox"${field.required?' checked':''}> ${t('required_short')}</label>
    <button class="secondary small" onclick="moveField(this,-1)">↑</button>
    <button class="secondary small" onclick="moveField(this,1)">↓</button>
    <button class="secondary small" onclick="toggleField(this)">${field.active===0?t('reactivate'):t('hide')}</button>
    <input class="fopts options" placeholder="${esc(t('list_options_placeholder'))}" value="${esc(field.options||'')}">
    <input class="fplaceholder options" placeholder="${esc(t('field_example_placeholder'))}" value="${esc(field.placeholder||'')}">
  `;
  row.querySelector('.ftype').value=field.field_type||'text';
  $('typeFields').appendChild(row);
  enableVoiceInputs(row);
  row.querySelector('.flabel').addEventListener('input',()=>refreshSubgroupFieldOptions($('tSubgroupField').value));
  refreshSubgroupFieldOptions($('tSubgroupField')?.value||'');
}

function moveField(btn,dir){
  const row=btn.parentElement, parent=row.parentElement;
  if(dir<0 && row.previousElementSibling) parent.insertBefore(row,row.previousElementSibling);
  if(dir>0 && row.nextElementSibling) parent.insertBefore(row.nextElementSibling,row);
}

function toggleField(btn){
  const row=btn.parentElement;
  const active=row.dataset.active!=='0';
  row.dataset.active=active?'0':'1';
  row.classList.toggle('inactive',active);
  btn.textContent=active?t('reactivate'):t('hide');
  refreshSubgroupFieldOptions($('tSubgroupField')?.value||'');
}

function editType(id){
  const typeDef=typeById(id);
  if(!typeDef)return;
  editingType=id;
  $('typeDlgTitle').textContent=t('edit_type');
  $('deleteTypeBtn').style.display='inline-block';
  $('tName').value=typeDef.name;
  $('tIconCustom').value=typeDef.icon;
  $('typeFields').innerHTML='';
  (typeDef.fields||[]).forEach(addFieldRow);
  refreshSubgroupFieldOptions(typeDef.subgroup_field_id||'');
  $('typeDlg').classList.add('show');
}

async function deleteType(){
  if(!editingType)return;
  const typeDef=typeById(editingType);
  const name=typeDef?typeDef.name:t('this_type');
  if(!confirm(tf('delete_type_confirm',{name})))return;
  try{
    await api('api/types/'+editingType,{method:'DELETE'});
    closeTypeDialog();
    await load();
  }catch(e){alert(e.message);}
}

async function saveType(){
  const fields=[...document.querySelectorAll('#typeFields .fieldrow')].map(row=>({
    id:row.dataset.id?Number(row.dataset.id):null,
    label:row.querySelector('.flabel').value,
    field_type:row.querySelector('.ftype').value,
    required:row.querySelector('.freq').checked,
    options:row.querySelector('.fopts').value,
    placeholder:row.querySelector('.fplaceholder').value,
    active:row.dataset.active!=='0'
  })).filter(f=>f.label.trim());

  const payload={
    name:$('tName').value,
    icon:$('tIconCustom').value.trim()||$('tIcon').value,
    subgroup_field_id:$('tSubgroupField').value||null,
    fields
  };

  try{
    if(editingType){
      await api('api/types/'+editingType,{method:'PUT',body:JSON.stringify(payload)});
    }else{
      await api('api/types',{method:'POST',body:JSON.stringify(payload)});
    }
    closeTypeDialog();
    await load();
  }catch(e){alert(e.message);}
}


function backupBytes(n){
  n=Number(n||0);
  if(n<1024)return n+' B';
  if(n<1024*1024)return (n/1024).toFixed(1)+' KB';
  return (n/1024/1024).toFixed(1)+' MB';
}

async function openBackupDialog(){
  $('backupDlg').classList.add('show');
  await loadBackupList();
}

function closeBackupDialog(){
  $('backupDlg').classList.remove('show');
}

function backupDate(value){
  if(!value) return "";
  const m=String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if(!m) return value;
  return `${m[3]}/${m[2]}/${m[1]} · ${m[4]}:${m[5]}:${m[6]}`;
}

async function loadBackupList(){
  const box=$('backupList');
  box.innerHTML=`<div class="hint">${t('loading_backups')}</div>`;

  try{
    const data=await api('api/backups');
    const rows=data.backups||[];

    const count=$('backupCount');
    if(count) count.textContent=rows.length;

    box.innerHTML=rows.length
      ? rows.map(b=>`
        <div class="backup-row">
          <div class="backup-row-name">${esc(b.filename)}</div>

          <div class="backup-row-meta">
            <span>🕒 ${esc(backupDate(b.modified))}</span>
            <span>💾 ${backupBytes(b.size)}</span>
            ${b.schema_version!==null && b.schema_version!==undefined
              ? `<span>${t('schema')} ${esc(b.schema_version)}</span>`
              : ''}
          </div>

          <div class="backup-row-status ${b.valid?'ok':'bad'}">
            ${b.valid
              ? `✓ ${t('backup_valid')}${b.items!==null?` · ${b.items} ${t('backup_items')}`:''}`
              : `⚠ ${esc(b.integrity||t('backup_invalid'))}`}
          </div>

          <div class="backup-row-actions">
            <a class="secondary backup-download"
               style="display:flex;align-items:center;justify-content:center;text-decoration:none;border-radius:10px;padding:8px"
               href="api/backups/download/${encodeURIComponent(b.filename)}">
              ${t('download')}
            </a>

            ${b.valid?`
              <button type="button"
                      class="backup-restore"
                      onclick="restoreBackupFromUi('${esc(b.filename)}')">
                ${t('restore')}
              </button>
            `:''}
          </div>
        </div>
      `).join('')
      : `<div class="empty">${t('no_backups')}</div>`;

  }catch(e){
    box.innerHTML=`<div class="notice">${t('error')}: ${esc(e.message)}</div>`;
  }
}

async function createManualBackup(){
  if(!confirm(t('create_backup_confirm')))return;

  try{
    const data=await api('api/backups/create',{
      method:'POST',
      body:JSON.stringify({})
    });

    alert(tf('backup_created',{filename:data.filename}));

    await loadBackupList();

  }catch(e){
    alert(e.message);
  }
}

async function restoreBackupFromUi(filename){
  if(!confirm(tf('restore_backup_confirm',{filename})))return;

  const confirmation=prompt(t('restore_type_word'));

  if(confirmation!=='RIPRISTINA'){
    alert(t('restore_cancelled'));
    return;
  }

  try{
    const data=await api('api/backups/restore',{
      method:'POST',
      body:JSON.stringify({filename})
    });

    let message=
      t('database_restored')+'\\n\\n'+
      t('items')+': '+(data.database?.items??'?')+'\\n'+
      t('types')+': '+(data.database?.types??'?')+'\\n'+
      t('photos')+': '+(data.database?.photos??'?')+'\\n'+
      t('integrity_check')+': '+(data.database?.integrity??'?');

    if(data.safety_backup){
      message+='\\n\\n'+t('previous_db_backup')+'\\n'+
        data.safety_backup;
    }

    if(data.safety_warning){
      message+='\\n\\n'+t('previous_db_warning')+'\\n'+
        data.safety_warning;
    }

    alert(message);

    closeBackupDialog();
    await load();

  }catch(e){
    alert(
      t('restore_failed')+'\\n\\n'+e.message+
      '\\n\\n'+t('selected_backup_kept')
    );
    await loadBackupList();
  }
}


$('search').addEventListener('keydown',e=>{if(e.key==='Enter')load();});

syncHomeAssistantTheme();
applyLanguage();
updateSearchClear();

window.addEventListener('focus',syncHomeAssistantTheme);
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden)syncHomeAssistantTheme();
});

setTypePanelCollapsed(localStorage.getItem('inventario_type_panel_collapsed')==='1');
load();

// v0.1.20 - porta automaticamente il campo attivo nella zona visibile su smartphone
let mobileFocusTimer=null;

function ensureFocusedFieldVisible(el){
  if(!el || !window.matchMedia('(max-width: 700px)').matches) return;

  clearTimeout(mobileFocusTimer);
  mobileFocusTimer=setTimeout(()=>{
    try{
      el.scrollIntoView({
        behavior:'smooth',
        block:'center',
        inline:'nearest'
      });
    }catch(e){
      el.scrollIntoView();
    }
  },220);
}

document.addEventListener('focusin',e=>{
  const el=e.target;
  if(!el.matches('input,select,textarea')) return;
  ensureFocusedFieldVisible(el);
});

if(window.visualViewport){
  let lastViewportHeight=window.visualViewport.height;

  window.visualViewport.addEventListener('resize',()=>{
    const active=document.activeElement;
    if(!active || !active.matches?.('input,select,textarea')) return;

    const current=window.visualViewport.height;
    const keyboardLikelyOpen=current < lastViewportHeight - 80 || current < window.innerHeight * .82;

    if(keyboardLikelyOpen){
      ensureFocusedFieldVisible(active);
    }

    lastViewportHeight=current;
  });

  window.visualViewport.addEventListener('scroll',()=>{
    const active=document.activeElement;
    if(active && active.matches?.('input,textarea')){
      ensureFocusedFieldVisible(active);
    }
  });
}



// =========================================================
// INVENTARIO CASA - SIDEBAR v1
// =========================================================

function isSidebarMobile(){
  return window.matchMedia('(max-width: 900px)').matches;
}

function toggleAppSidebar(){
  if(isSidebarMobile()){
    document.body.classList.toggle('sidebar-mobile-open');
  }else{
    toggleSidebarCollapsed();
  }
}

function closeAppSidebar(){
  document.body.classList.remove('sidebar-mobile-open');
}

function toggleSidebarCollapsed(){
  if(isSidebarMobile()){
    closeAppSidebar();
    return;
  }

  document.body.classList.toggle('sidebar-collapsed');

  try{
    localStorage.setItem(
      'inventarioSidebarCollapsed',
      document.body.classList.contains('sidebar-collapsed') ? '1' : '0'
    );
  }catch(e){}
}

function sidebarSetActive(index){
  document.querySelectorAll('.sidebar-item').forEach((el,i)=>{
    el.classList.toggle('active', i === index);
  });
}

function sidebarGoInventory(){
  sidebarSetActive(0);
  closeAppSidebar();

  const target =
    document.getElementById('items') ||
    document.querySelector('main');

  if(target){
    target.scrollIntoView({
      behavior:'smooth',
      block:'start'
    });
  }
}

function sidebarNewItem(){
  sidebarSetActive(1);
  closeAppSidebar();

  const panel = document.getElementById('newItemPanel');

  if(panel){
    if(panel.classList.contains('collapsed') &&
       typeof toggleNewItemPanel === 'function'){
      toggleNewItemPanel();
    }

    setTimeout(()=>{
      panel.scrollIntoView({
        behavior:'smooth',
        block:'start'
      });
    },50);
  }
}

function sidebarTypes(){
  sidebarSetActive(2);
  closeAppSidebar();

  const panel = document.getElementById('typePanel');

  if(panel){
    panel.scrollIntoView({
      behavior:'smooth',
      block:'start'
    });
  }
}

function sidebarBackup(){
  sidebarSetActive(3);
  closeAppSidebar();

  if(typeof openBackupDialog === 'function'){
    openBackupDialog();
  }
}

(function initInventorySidebar(){

  try{
    if(!isSidebarMobile() &&
       localStorage.getItem('inventarioSidebarCollapsed') === '1'){
      document.body.classList.add('sidebar-collapsed');
    }
  }catch(e){}

  window.addEventListener('resize',()=>{
    if(!isSidebarMobile()){
      document.body.classList.remove('sidebar-mobile-open');
    }
  });

  document.addEventListener('keydown',(event)=>{
    if(event.key === 'Escape'){
      closeAppSidebar();
    }
  });

})();


// =========================================================
// INVENTARIO CASA - SIDEBAR v2 / NAVIGAZIONE
// =========================================================

function sidebarShowView(viewId, menuIndex){
  const clearedSearch=viewId !== 'inventoryView' && !!$('search')?.value.trim();

  if(viewId !== 'inventoryView'){
    const topbar=$('appTopbar');
    const input=$('search');

    if(input){
      input.value='';
      clearTimeout(searchDebounceTimer);
      updateSearchClear();
      clearTimeout(searchDebounceTimer);
    }

    if(topbar){
      topbar.classList.remove('search-open');
    }

    document.body.classList.remove('header-search-active');
  }

  document.querySelectorAll('.app-view').forEach(view=>{
    view.classList.remove('active');
  });

  const view = document.getElementById(viewId);

  if(view){
    view.classList.add('active');
  }

  const stats=document.querySelector('.stats');
  if(stats){
    stats.style.display=(viewId==='inventoryView') ? '' : 'none';
  }

  sidebarSetActive(menuIndex);
  closeAppSidebar();

  window.scrollTo({
    top:0,
    behavior:'smooth'
  });
  if(clearedSearch) load().catch(e=>alert(e.message));
}

/*
 * Queste funzioni sostituiscono intenzionalmente
 * il comportamento della Sidebar v1.
 */

function sidebarGoInventory(){
  sidebarShowView('inventoryView',0);
}

function sidebarNewItem(){

  sidebarShowView('inventoryView',1);

  const panel = document.getElementById('newItemPanel');

  if(panel){

    if(panel.classList.contains('collapsed') &&
       typeof toggleNewItemPanel === 'function'){
      toggleNewItemPanel();
    }

    setTimeout(()=>{
      panel.scrollIntoView({
        behavior:'smooth',
        block:'start'
      });
    },80);
  }
}

function sidebarTypes(){

  sidebarShowView('typesView',2);

  if(typeof renderTypes === 'function'){
    renderTypes();
  }
}

function sidebarBackup(){

  sidebarSetActive(3);
  closeAppSidebar();

  if(typeof openBackupDialog === 'function'){
    openBackupDialog();
  }
}

// =========================================================
// SIDEBAR v2 - HOME PULITA
// =========================================================

function sidebarGoInventory(){
  document.body.classList.remove('show-new-item');
  sidebarShowView('inventoryView',0);
}

function sidebarNewItem(){

  document.body.classList.add('show-new-item');

  sidebarShowView('inventoryView',1);

  const panel=document.getElementById('newItemPanel');

  if(panel){

    if(panel.classList.contains('collapsed') &&
       typeof toggleNewItemPanel==='function'){
      toggleNewItemPanel();
    }

    setTimeout(()=>{
      panel.scrollIntoView({
        behavior:'smooth',
        block:'start'
      });
    },80);
  }
}

function sidebarTypes(){
  document.body.classList.remove('show-new-item');

  sidebarShowView('typesView',2);

  if(typeof renderTypes==='function'){
    renderTypes();
  }
}

function sidebarBackup(){

  document.body.classList.remove('show-new-item');

  sidebarSetActive(3);
  closeAppSidebar();

  if(typeof openBackupDialog==='function'){
    openBackupDialog();
  }
}


// =========================================================
// SIDEBAR v2 - BACKUP COME PAGINA
// =========================================================

function sidebarBackup(){
  document.body.classList.remove('show-new-item');

  sidebarShowView('backupView',3);

  if(typeof loadBackupList === 'function'){
    loadBackupList();
  }
}


// =========================================================
// SIDEBAR v2 - NUOVO ELEMENTO COME PAGINA
// =========================================================

function sidebarGoInventory(){
  document.body.classList.remove('show-new-item');
  sidebarShowView('inventoryView',0);
}

function sidebarNewItem(){
  document.body.classList.remove('show-new-item');
  sidebarShowView('newItemView',1);

  loadAddLocations();

  const panel=document.getElementById('newItemPanel');

  if(panel){
    panel.classList.remove('collapsed');

    const head=panel.querySelector('.new-item-head');
    if(head){
      head.setAttribute('aria-expanded','true');
    }
  }
}

function sidebarTypes(){
  document.body.classList.remove('show-new-item');
  sidebarShowView('typesView',2);

  if(typeof renderTypes==='function'){
    renderTypes();
  }
}

function sidebarBackup(){
  document.body.classList.remove('show-new-item');
  sidebarShowView('backupView',3);

  if(typeof loadBackupList==='function'){
    loadBackupList();
  }
}



// =========================================================
// SIDEBAR - IMPOSTAZIONI
// =========================================================

function sidebarSettings(){
  document.body.classList.remove('show-new-item');
  sidebarShowView('settingsView',4);
}


document.addEventListener('DOMContentLoaded',()=>{
  syncPageSizeSetting();
});

/* ===== Proprietà e ambienti ===== */

let locationsData = [];
let selectedPropertyId = null;

async function openLocationsDialog(){
  const dlg = $('locationsDlg');
  if(!dlg) return;

  dlg.style.display = 'flex';
  await loadLocations();
}

function closeLocationsDialog(){
  const dlg = $('locationsDlg');
  if(dlg) dlg.style.display = 'none';
}

async function loadLocations(){
  const res = await fetch('api/properties');
  const data = await res.json();

  locationsData = data.properties || [];

  if(!locationsData.length){
    selectedPropertyId = null;
  }else if(!locationsData.some(p => p.id === selectedPropertyId)){
    const def = locationsData.find(p => p.is_default);
    selectedPropertyId = (def || locationsData[0]).id;
  }

  renderLocations();
}

function renderLocations(){
  const properties = $('propertiesList');
  const environments = $('environmentsList');

  if(!properties || !environments) return;

  const environmentsTitle = $('environmentsColumnTitle');
  const selectedForTitle = locationsData.find(
    p => p.id === selectedPropertyId
  );

  if(environmentsTitle){
    environmentsTitle.textContent = selectedForTitle
      ? `Ambienti di: ${selectedForTitle.name}`
      : 'Ambienti';
  }

  properties.innerHTML = '';

  locationsData.forEach(prop => {
    const wrap = document.createElement('div');
    wrap.className = 'location-item';

    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'secondary location-row' +
      (prop.id === selectedPropertyId ? ' active' : '');

    row.textContent = prop.name;

    row.onclick = () => {
      selectedPropertyId = prop.id;
      renderLocations();
    };

    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'secondary location-action';
    edit.textContent = '✏️';
    edit.title = t('rename');
    edit.onclick = () => renameProperty(prop);

    const action = document.createElement('button');
    action.type = 'button';
    action.className = prop.is_default
      ? 'secondary location-action'
      : 'danger location-action';

    if(prop.is_default){
      action.textContent = '★';
      action.title = t('default_property');
      action.disabled = true;
    }else{
      action.textContent = '🗑️';
      action.title = t('delete');
      action.onclick = () => deletePropertyLocation(prop);
    }

    const makeDefault = document.createElement('button');
    makeDefault.type = 'button';
    makeDefault.className = 'secondary location-action';
    makeDefault.textContent = '☆︎';
    makeDefault.title = t('set_default_property');
    makeDefault.onclick = () => setDefaultProperty(prop);

    wrap.append(row, edit);

    if(!prop.is_default){
      wrap.append(makeDefault);
    }

    wrap.append(action);
    properties.appendChild(wrap);
  });

  environments.innerHTML = '';

  const selected = locationsData.find(
    p => p.id === selectedPropertyId
  );

  (selected?.environments || []).forEach(env => {
    const wrap = document.createElement('div');
    wrap.className = 'location-item';

    const row = document.createElement('div');
    row.className = 'location-row';
    row.textContent = env.name;

    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'secondary location-action';
    edit.textContent = '✏️';
    edit.title = t('rename');
    edit.onclick = () => renameEnvironment(env);

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'danger location-action';
    del.textContent = '🗑️';
    del.title = t('delete');
    del.onclick = () => deleteEnvironmentLocation(env);

    wrap.append(row, edit, del);
    environments.appendChild(wrap);
  });

  const addBtn = $('addEnvironmentBtn');
  if(addBtn) addBtn.disabled = !selected;
}

const manageLocationsBtn = $('manageLocationsBtn');
if(manageLocationsBtn){
  manageLocationsBtn.onclick = openLocationsDialog;
}

async function addProperty(){
  const name = prompt(t('property_name_prompt') || 'Nome del nuovo luogo:');

  if(!name || !name.trim()) return;

  const res = await fetch('api/properties', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      name: name.trim()
    })
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  selectedPropertyId = data.property.id;
  await loadLocations();
}

async function addEnvironment(){
  if(!selectedPropertyId) return;

  const name = prompt(t('environment_name_prompt') || 'Nome del nuovo ambiente:');

  if(!name || !name.trim()) return;

  const res = await fetch('api/environments', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      property_id: selectedPropertyId,
      name: name.trim()
    })
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  await loadLocations();
}

async function renameProperty(prop){
  const name = prompt(t('rename_property_prompt'), prop.name);
  if(!name || !name.trim() || name.trim() === prop.name) return;

  const res = await fetch(`api/properties/${prop.id}`, {
    method:'PUT',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name.trim()})
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  await loadLocations();
}

async function deletePropertyLocation(prop){
  if(!confirm(tf('delete_property_confirm', {name:prop.name}))) return;

  const res = await fetch(`api/properties/${prop.id}`, {
    method:'DELETE'
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  selectedPropertyId = null;
  await loadLocations();
}

async function renameEnvironment(env){
  const name = prompt(t('rename_environment_prompt'), env.name);
  if(!name || !name.trim() || name.trim() === env.name) return;

  const res = await fetch(`api/environments/${env.id}`, {
    method:'PUT',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name.trim()})
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  await loadLocations();
}

async function deleteEnvironmentLocation(env){
  if(!confirm(tf('delete_environment_confirm', {name:env.name}))) return;

  const res = await fetch(`api/environments/${env.id}`, {
    method:'DELETE'
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  await loadLocations();
}

async function setDefaultProperty(prop){
  const res = await fetch(`api/properties/${prop.id}/default`, {
    method:'PUT'
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || 'Errore');
    return;
  }

  await loadLocations();
}

async function loadAddLocations(){
  if(!locationsData.length){
    const res = await fetch('api/properties');
    const data = await res.json();
    locationsData = data.properties || [];
  }

  const select = $('aProperty');
  if(!select) return;

  select.innerHTML = '';

  locationsData.forEach(prop => {
    const option = document.createElement('option');
    option.value = prop.id;
    option.textContent = prop.name;

    if(prop.is_default){
      option.selected = true;
    }

    select.appendChild(option);
  });

  updateAddEnvironments();
}

function updateAddEnvironments(){
  const propertySelect = $('aProperty');
  const environmentSelect = $('aEnv');

  if(!propertySelect || !environmentSelect) return;

  const propertyId = Number(propertySelect.value);

  const prop = locationsData.find(
    p => p.id === propertyId
  );

  environmentSelect.innerHTML = '';

  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = '—';
  environmentSelect.appendChild(empty);

  (prop?.environments || [])
    .filter(env => env.active)
    .forEach(env => {
      const option = document.createElement('option');
      option.value = env.name;
      option.dataset.environmentId = env.id;
      option.textContent = env.name;
      environmentSelect.appendChild(option);
    });
}

async function loadEditLocations(currentEnvironment='', currentEnvironmentId=null){
  if(!locationsData.length){
    const res = await fetch('api/properties');
    const data = await res.json();
    locationsData = data.properties || [];
  }

  const propertySelect = $('eProperty');
  if(!propertySelect) return;

  propertySelect.innerHTML = '';

  let matchedProperty = null;

  if(currentEnvironmentId){
    matchedProperty = locationsData.find(prop =>
      (prop.environments || []).some(
        env => env.id === Number(currentEnvironmentId)
      )
    );
  }

  if(!matchedProperty && currentEnvironment){
    matchedProperty = locationsData.find(prop =>
      (prop.environments || []).some(
        env => env.name === currentEnvironment
      )
    );
  }

  if(!matchedProperty){
    matchedProperty =
      locationsData.find(prop => prop.is_default) ||
      locationsData[0] ||
      null;
  }

  locationsData.forEach(prop => {
    const option = document.createElement('option');
    option.value = prop.id;
    option.textContent = prop.name;
    option.selected = matchedProperty?.id === prop.id;
    propertySelect.appendChild(option);
  });

  updateEditEnvironments(currentEnvironment, currentEnvironmentId);
}

function updateEditEnvironments(currentEnvironment='', currentEnvironmentId=null){
  const propertySelect = $('eProperty');
  const environmentSelect = $('eEnv');

  if(!propertySelect || !environmentSelect) return;

  const propertyId = Number(propertySelect.value);
  const prop = locationsData.find(p => p.id === propertyId);

  environmentSelect.innerHTML = '';

  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = '—';
  environmentSelect.appendChild(empty);

  (prop?.environments || [])
    .filter(env => env.active)
    .forEach(env => {
      const option = document.createElement('option');
      option.value = env.name;
      option.dataset.environmentId = env.id;
      option.textContent = env.name;
      environmentSelect.appendChild(option);
    });

  if(currentEnvironmentId){
    const option = [...environmentSelect.options].find(
      option => Number(option.dataset.environmentId) === Number(currentEnvironmentId)
    );

    if(option){
      environmentSelect.value = option.value;
      return;
    }
  }

  if(currentEnvironment){
    const exists = [...environmentSelect.options]
      .some(option => option.value === currentEnvironment);

    if(!exists){
      const legacy = document.createElement('option');
      legacy.value = currentEnvironment;
      legacy.textContent = currentEnvironment;
      environmentSelect.appendChild(legacy);
    }

    environmentSelect.value = currentEnvironment;
  }
}
