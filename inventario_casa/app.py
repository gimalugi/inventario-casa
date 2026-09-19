from flask import Flask, render_template, render_template_string, send_from_directory
import os
from pathlib import Path
import json
import threading
from frontend import FRONTEND_ASSETS, asset_version, load_translations
from backup_routes import create_backup_blueprint
from media_routes import create_media_blueprint
from type_routes import create_type_blueprint
from item_routes import create_item_blueprint
from lookup_routes import create_lookup_blueprint
from inventory_routes import create_inventory_blueprint
from backup_restore import restore_database_backup as backup_restore_database
from database import (
    db as database_connect,
    table_columns,
    read_schema_version as database_read_schema_version,
    write_schema_version,
    ensure_column,
    ensure_type_field,
    init_db as database_init,
)

APP_NAME = "Inventario Casa"

def env_int(name, default, minimum=1):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


BACKUP_KEEP_MANUAL = env_int("INVENTORY_BACKUP_KEEP_MANUAL", 10)
BACKUP_KEEP_PRE_RESTORE = env_int("INVENTORY_BACKUP_KEEP_PRE_RESTORE", 5)
BACKUP_KEEP_PRE_SCHEMA = env_int("INVENTORY_BACKUP_KEEP_PRE_SCHEMA", 5)
DATA_DIR = Path("/data/inventario_casa")
DB_PATH = DATA_DIR / "inventario.db"
MEDIA_DIR = Path("/media/inventario_casa/oggetti")
DB_BACKUP_DIR = Path("/media/inventario_casa/db_backups")

CURRENT_SCHEMA_VERSION = 1

DB_MAINTENANCE_LOCK = threading.Lock()
STARTUP_DB_ERROR = None

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024



def db():
    return database_connect(DB_PATH, DATA_DIR, MEDIA_DIR)


def read_schema_version():
    return database_read_schema_version(DB_PATH)




def set_startup_db_error(value):
    global STARTUP_DB_ERROR
    STARTUP_DB_ERROR = value


def restore_database_backup(filename):
    return backup_restore_database(
        filename,
        db_path=DB_PATH,
        data_dir=DATA_DIR,
        backup_dir=DB_BACKUP_DIR,
        maintenance_lock=DB_MAINTENANCE_LOCK,
        backup_keep_pre_restore=BACKUP_KEEP_PRE_RESTORE,
        init_db=init_db,
        set_startup_error=set_startup_db_error,
    )


def init_db():
    return database_init(
        DB_PATH,
        DATA_DIR,
        MEDIA_DIR,
        DB_BACKUP_DIR,
        CURRENT_SCHEMA_VERSION,
        BACKUP_KEEP_PRE_SCHEMA,
    )

try:
    init_db()
except Exception as exc:
    STARTUP_DB_ERROR = f"{type(exc).__name__}: {exc}"
    print(
        "[Inventario Casa] ERRORE inizializzazione database. "
        "Avvio modalità Recovery: "
        + STARTUP_DB_ERROR
    )


app.register_blueprint(
    create_inventory_blueprint(
        db=db,
    )
)


app.register_blueprint(
    create_lookup_blueprint()
)


app.register_blueprint(
    create_backup_blueprint(
        db_path=DB_PATH,
        backup_dir=DB_BACKUP_DIR,
        maintenance_lock=DB_MAINTENANCE_LOCK,
        backup_keep_manual=BACKUP_KEEP_MANUAL,
        get_startup_error=lambda: STARTUP_DB_ERROR,
        restore_database_backup=restore_database_backup,
    )
)


app.register_blueprint(
    create_item_blueprint(
        db=db,
        media_dir=MEDIA_DIR,
    )
)


app.register_blueprint(
    create_type_blueprint(
        db=db,
    )
)


app.register_blueprint(
    create_media_blueprint(
        db=db,
        media_dir=MEDIA_DIR,
    )
)

RECOVERY_PAGE = r"""
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inventario Casa - Recovery</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{
  margin:0;
  min-height:100vh;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  color:#f7f9fb;
  background:
    radial-gradient(circle at 10% 5%,#185b78 0%,transparent 38%),
    radial-gradient(circle at 90% 10%,#8e3348 0%,transparent 40%),
    linear-gradient(145deg,#123f58,#24204c 48%,#8e3348);
  padding:18px;
}
.wrap{max-width:720px;margin:auto}
.card{
  margin-bottom:14px;
  padding:16px;
  border-radius:16px;
  border:1.5px solid rgba(255,255,255,.42);
  background:rgba(255,255,255,.12);
  backdrop-filter:blur(12px);
}
h1,h2{margin-top:0}
.error{
  white-space:pre-wrap;
  word-break:break-word;
  padding:12px;
  border-radius:10px;
  border:1px solid #ff7b7b;
  background:rgba(120,20,30,.22);
}
.backup{
  padding:12px;
  border:1px solid rgba(255,255,255,.32);
  border-radius:12px;
  margin:8px 0;
  background:rgba(0,0,0,.15);
}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
button,a.btn{
  border-radius:10px;
  border:1px solid rgba(255,255,255,.38);
  padding:9px 12px;
  font:inherit;
  font-weight:700;
  cursor:pointer;
  text-decoration:none;
  background:#55aef7;
  color:#07111c;
}
.secondary{background:rgba(255,255,255,.12)!important;color:#fff!important}
.ok{color:#72e49d}.bad{color:#ff9b9b}.muted{color:#c7ced7}
/* v2.3.0 - Backup & Recovery */
.backup-panel-head{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:8px;
}
.backup-panel-head h2{margin:0!important}
.backup-list{display:grid;gap:9px;margin-top:12px}
.backup-row{
  padding:11px;
  border:1.5px solid rgba(255,255,255,.38);
  border-radius:12px;
  background:rgba(0,0,0,.14);
}
.backup-row-name{
  font-weight:800;
  overflow-wrap:anywhere;
}
.backup-row-meta{
  margin-top:3px;
  font-size:.78rem;
  color:var(--inv-muted,var(--muted));
}
.backup-row-status{
  margin-top:5px;
  font-size:.82rem;
}
.backup-row-status.ok{color:#72e49d}
.backup-row-status.bad{color:#ff9b9b}
.backup-row-actions{
  display:flex;
  gap:7px;
  flex-wrap:wrap;
  margin-top:9px;
}
.backup-row-actions button,
.backup-row-actions a{
  flex:1;
  min-width:110px;
}
.backup-info{
  margin:10px 0;
  padding:10px;
  border:1.5px solid rgba(79,176,255,.40);
  border-radius:11px;
  background:rgba(79,176,255,.07);
}
@media(max-width:640px){
  .backup-row-actions{
    display:grid;
    grid-template-columns:1fr 1fr;
  }
}


</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1 id="recoveryTitle">🛟 Inventario Casa - Recovery</h1>
    <p id="recoveryDescription">
      Inventario Casa non è riuscito ad aprire o aggiornare correttamente
      il database. I backup restano disponibili.
    </p>
    <div class="error">{{ startup_error }}</div>
  </div>

  <div class="card">
    <h2 id="recoveryBackupsTitle">Backup disponibili</h2>
    <div id="backups">Caricamento…</div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);

const RECOVERY_I18N={
  it:{
    title:'🛟 Inventario Casa - Recovery',
    description:'Inventario Casa non è riuscito ad aprire o aggiornare correttamente il database. I backup restano disponibili.',
    available_backups:'Backup disponibili',
    loading:'Caricamento…',
    valid_backup:'✓ Backup integro',
    items:'elementi',
    types:'tipologie',
    photos:'foto',
    download:'Scarica',
    restore:'Ripristina',
    no_backups:'Nessun backup disponibile.',
    error:'Errore',
    restore_confirm:'Ripristinare questo backup?\n\n{name}\n\nIl database corrente verrà sostituito.',
    restore_keyword:'Per confermare il ripristino scrivi:\n\nRIPRISTINA',
    restore_failed:'Ripristino non riuscito',
    restore_ok:'Backup ripristinato correttamente.',
    integrity:'Integrity check'
  },
  en:{
    title:'🛟 Home Inventory - Recovery',
    description:'Home Inventory could not open or update the database correctly. Backups remain available.',
    available_backups:'Available backups',
    loading:'Loading…',
    valid_backup:'✓ Valid backup',
    items:'items',
    types:'types',
    photos:'photos',
    download:'Download',
    restore:'Restore',
    no_backups:'No backups available.',
    error:'Error',
    restore_confirm:'Restore this backup?\n\n{name}\n\nThe current database will be replaced.',
    restore_keyword:'To confirm the restore, type:\n\nRIPRISTINA',
    restore_failed:'Restore failed',
    restore_ok:'Backup restored successfully.',
    integrity:'Integrity check'
  }
};

function recoveryLanguage(){
  try{
    if(window.parent && window.parent!==window){
      const lang=(
        window.parent.document.documentElement.lang||''
      ).toLowerCase();

      if(lang.startsWith('en')) return 'en';
      if(lang.startsWith('it')) return 'it';
    }
  }catch(e){}

  const lang=(navigator.language||'it').toLowerCase();
  return lang.startsWith('en')?'en':'it';
}

const recoveryLang=recoveryLanguage();

function rt(key){
  return RECOVERY_I18N[recoveryLang]?.[key]
      ?? RECOVERY_I18N.it[key]
      ?? key;
}

function rtf(key,vars={}){
  return rt(key).replace(/\{(\w+)\}/g,(_,name)=>
    Object.prototype.hasOwnProperty.call(vars,name)
      ? vars[name]
      : `{${name}}`
  );
}

document.documentElement.lang=recoveryLang;
$('recoveryTitle').textContent=rt('title');
$('recoveryDescription').textContent=rt('description');
$('recoveryBackupsTitle').textContent=rt('available_backups');
$('backups').textContent=rt('loading');

const esc=s=>String(s??'')
 .replaceAll('&','&amp;')
 .replaceAll('<','&lt;')
 .replaceAll('>','&gt;')
 .replaceAll('"','&quot;');

function bytes(n){
  n=Number(n||0);
  if(n<1024)return n+' B';
  if(n<1024*1024)return (n/1024).toFixed(1)+' KB';
  return (n/1024/1024).toFixed(1)+' MB';
}

async function loadBackups(){
  try{
    const r=await fetch('api/backups');
    const d=await r.json();
    const rows=d.backups||[];

    $('backups').innerHTML=rows.length
      ? rows.map(b=>`
        <div class="backup">
          <strong>${esc(b.filename)}</strong><br>
          <span class="muted">${esc(b.modified)} · ${bytes(b.size)}</span><br>
          <span class="${b.valid?'ok':'bad'}">
            ${b.valid?rt('valid_backup'):'⚠ '+esc(b.integrity)}
          </span>
          ${b.items!==null
            ? `<div class="muted">${b.items} ${rt('items')} · ${b.types??'?'} ${rt('types')} · ${b.photos??'?'} ${rt('photos')}</div>`
            : ''}
          <div class="actions">
            <a class="btn secondary"
               href="api/backups/download/${encodeURIComponent(b.filename)}">
               ${rt('download')}
            </a>
            ${b.valid?`
              <button onclick="restoreBackup('${esc(b.filename)}')">
                ${rt('restore')}
              </button>`:''}
          </div>
        </div>
      `).join('')
      : `<div class="muted">${rt('no_backups')}</div>`;

  }catch(e){
    $('backups').textContent=rt('error')+': '+e.message;
  }
}

async function restoreBackup(name){
  if(!confirm(rtf('restore_confirm',{name})))return;

  const confirmText=prompt(rt('restore_keyword'));

  if(confirmText!=='RIPRISTINA')return;

  const r=await fetch('api/backups/restore',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({filename:name})
  });

  const d=await r.json().catch(()=>({}));

  if(!r.ok){
    alert(d.error||rt('restore_failed'));
    await loadBackups();
    return;
  }

  alert(
    rt('restore_ok')+'\n\n'+
    rt('items')+': '+(d.database?.items??'?')+'\n'+
    rt('integrity')+': '+(d.database?.integrity??'?')
  );

  location.reload();
}

loadBackups();
</script>
</body>
</html>
"""





FRONTEND_ASSET_VERSION = asset_version(app.static_folder)
FRONTEND_TRANSLATIONS = load_translations(app.static_folder)


@app.get("/assets/<version>/<path:filename>")
def frontend_asset(version, filename):
    if version != FRONTEND_ASSET_VERSION:
        return "", 404

    if filename not in FRONTEND_ASSETS:
        return "", 404

    return send_from_directory(app.static_folder, filename)


@app.get("/")
def index():
    if STARTUP_DB_ERROR:
        return render_template_string(
            RECOVERY_PAGE,
            startup_error=STARTUP_DB_ERROR,
        )
    return render_template(
        "index.html",
        asset_version=FRONTEND_ASSET_VERSION,
        translations=FRONTEND_TRANSLATIONS,
        default_language=os.environ.get("INVENTORY_LANGUAGE", "it"),
    )

