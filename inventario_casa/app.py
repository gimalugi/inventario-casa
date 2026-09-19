from flask import Flask, request, jsonify, render_template, render_template_string, send_from_directory
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


def type_rows(conn):
    result = [dict(r) for r in conn.execute(
        "SELECT id,name,icon,subgroup_field_id FROM item_types ORDER BY name COLLATE NOCASE"
    )]
    for t in result:
        t["fields"] = [dict(r) for r in conn.execute(
            """SELECT id,label,field_type,required,options,sort_order,active,placeholder
               FROM type_fields
               WHERE type_id=?
               ORDER BY sort_order,id""",
            (t["id"],),
        )]
    return result


def item_custom_values(conn, item_id):
    return {
        str(r["field_id"]): r["value"]
        for r in conn.execute(
            "SELECT field_id,value FROM item_custom_values WHERE item_id=?",
            (item_id,),
        )
    }


def distinct_values(conn, column):
    return [
        r["v"]
        for r in conn.execute(
            f"""SELECT DISTINCT {column} AS v
                FROM items
                WHERE TRIM(COALESCE({column},'')) <> ''
                ORDER BY v COLLATE NOCASE"""
        )
    ]


@app.get("/api/bootstrap")
def api_bootstrap():
    q = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "20"))
    except (TypeError, ValueError):
        limit = 20
    if limit not in {20, 50, 100}:
        limit = 20

    with db() as conn:
        types = type_rows(conn)

        where_sql = ""
        params = []
        if q:
            like = f"%{q}%"
            cols = [
                "i.name", "i.description", "i.tags", "i.notes",
                "i.environment", "i.furniture", "i.shelf",
                "i.container_name", "i.container_code"
            ]
            where_sql = " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols)
            where_sql += """ OR EXISTS(
                SELECT 1 FROM item_custom_values cv
                WHERE cv.item_id=i.id AND cv.value LIKE ?
            )"""
            params = [like] * (len(cols) + 1)

        matched_count = conn.execute(
            "SELECT COUNT(*) FROM items i" + where_sql,
            params,
        ).fetchone()[0]

        sql = """
            SELECT i.*, t.name AS type_name, t.icon AS type_icon
            FROM items i
            LEFT JOIN item_types t ON t.id=i.item_type_id
        """ + where_sql
        sql += " ORDER BY i.updated_at DESC, i.name COLLATE NOCASE LIMIT ?"

        items = [dict(r) for r in conn.execute(sql, [*params, limit])]
        for item in items:
            item["custom_values"] = item_custom_values(conn, item["id"])
            item["photos"] = [dict(r) for r in conn.execute(
                """SELECT id,filename,thumb_filename,COALESCE(label,'') AS label
                   FROM item_photos
                   WHERE item_id=?
                   ORDER BY id""",
                (item["id"],),
            )]
            item["position_path"] = " → ".join(
                x for x in [
                    item["environment"],
                    item["furniture"],
                    item["shelf"],
                    item["container_name"],
                ] if x
            )

        envs = distinct_values(conn, "environment")
        return jsonify(
            types=types,
            items=items,
            list_limit=limit,
            matched_count=matched_count,
            suggestions={
                "environment": envs,
                "furniture": distinct_values(conn, "furniture"),
                "shelf": distinct_values(conn, "shelf"),
                "container": distinct_values(conn, "container_name"),
            },
            counts={
                "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
                "environments": len(envs),
                "types": len(types),
            }
        )



def inventory_search_where(q):
    q = (q or "").strip()
    if not q:
        return "", []
    like = f"%{q}%"
    cols = [
        "i.name", "i.description", "i.tags", "i.notes",
        "i.environment", "i.furniture", "i.shelf",
        "i.container_name", "i.container_code"
    ]
    where_sql = " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols)
    where_sql += """ OR EXISTS(
        SELECT 1 FROM item_custom_values cv
        WHERE cv.item_id=i.id AND cv.value LIKE ?
    )"""
    return where_sql, [like] * (len(cols) + 1)


def append_inventory_condition(where_sql, condition):
    if not condition:
        return where_sql
    if where_sql:
        return where_sql + " AND " + condition
    return " WHERE " + condition


def inventory_sort_select_sql():
    # Se la tipologia possiede un campo attivo chiamato "Numero",
    # lo usa per l'ordinamento numerico. Per i tipi senza Numero
    # il normale ordinamento alfabetico resta invariato.
    return """
        , (
            SELECT cv_num.value
            FROM item_custom_values cv_num
            JOIN type_fields tf_num ON tf_num.id=cv_num.field_id
            WHERE cv_num.item_id=i.id
              AND tf_num.type_id=i.item_type_id
              AND tf_num.active=1
              AND LOWER(TRIM(tf_num.label))='numero'
            ORDER BY tf_num.sort_order, tf_num.id
            LIMIT 1
          ) AS _sort_num
        , (
            SELECT cv_suffix.value
            FROM item_custom_values cv_suffix
            JOIN type_fields tf_suffix ON tf_suffix.id=cv_suffix.field_id
            WHERE cv_suffix.item_id=i.id
              AND tf_suffix.type_id=i.item_type_id
              AND tf_suffix.active=1
              AND LOWER(TRIM(tf_suffix.label))='suffisso numero'
            ORDER BY tf_suffix.sort_order, tf_suffix.id
            LIMIT 1
          ) AS _sort_suffix
    """


def inventory_order_sql():
    return """
        ORDER BY
          CASE
            WHEN TRIM(COALESCE(_sort_num,''))='' THEN 1
            ELSE 0
          END,
          CASE
            WHEN TRIM(COALESCE(_sort_num,''))='' THEN 0
            ELSE CAST(REPLACE(_sort_num, ',', '.') AS REAL)
          END,
          CASE
            WHEN TRIM(COALESCE(_sort_suffix,''))='' THEN 0
            WHEN LOWER(TRIM(_sort_suffix))='bis' THEN 1
            ELSE 2
          END,
          i.name COLLATE NOCASE,
          i.id
    """


def hydrate_inventory_items(conn, rows):
    items = [dict(r) for r in rows]
    for item in items:
        item.pop("_sort_num", None)
        item.pop("_sort_suffix", None)
        item["custom_values"] = item_custom_values(conn, item["id"])
        item["photos"] = [dict(r) for r in conn.execute(
            """SELECT id,filename,thumb_filename,COALESCE(label,'') AS label
               FROM item_photos
               WHERE item_id=?
               ORDER BY id""",
            (item["id"],),
        )]
        item["position_path"] = " → ".join(
            x for x in [
                item.get("environment"),
                item.get("furniture"),
                item.get("shelf"),
                item.get("container_name"),
            ] if x
        )
    return items


@app.get("/api/inventory-groups")
def api_inventory_groups():
    q = request.args.get("q", "").strip()
    grouping = request.args.get("group_by", "type").strip().lower()
    if grouping not in {"type", "environment", "none"}:
        grouping = "type"

    where_sql, params = inventory_search_where(q)

    with db() as conn:
        if grouping == "type":
            sql = """
                SELECT
                    COALESCE(CAST(i.item_type_id AS TEXT),'none') AS group_key,
                    COALESCE(t.name,'Senza tipologia') AS label,
                    COALESCE(t.icon,'📦') AS icon,
                    COUNT(*) AS item_count
                FROM items i
                LEFT JOIN item_types t ON t.id=i.item_type_id
            """ + where_sql + """
                GROUP BY i.item_type_id, t.name, t.icon
                ORDER BY label COLLATE NOCASE
            """
        elif grouping == "environment":
            sql = """
                SELECT
                    CASE WHEN TRIM(COALESCE(i.environment,''))='' THEN '__none__' ELSE TRIM(i.environment) END AS group_key,
                    CASE WHEN TRIM(COALESCE(i.environment,''))='' THEN 'Senza ambiente' ELSE TRIM(i.environment) END AS label,
                    '🏠' AS icon,
                    COUNT(*) AS item_count
                FROM items i
            """ + where_sql + """
                GROUP BY CASE WHEN TRIM(COALESCE(i.environment,''))='' THEN '__none__' ELSE TRIM(i.environment) END
                ORDER BY label COLLATE NOCASE
            """
        else:
            count = conn.execute("SELECT COUNT(*) FROM items i" + where_sql, params).fetchone()[0]
            groups = [{"group_key":"all","label":"Tutti gli elementi","icon":"📦","item_count":count}] if count else []
            return jsonify(groups=groups, matched_count=count, page_size=50)

        groups = [dict(r) for r in conn.execute(sql, params)]
        matched_count = sum(int(g["item_count"]) for g in groups)
        return jsonify(groups=groups, matched_count=matched_count, page_size=50)


@app.get("/api/inventory-subgroups")
def api_inventory_subgroups():
    q = request.args.get("q", "").strip()
    try:
        type_id = int(request.args.get("type_id", "0"))
    except (TypeError, ValueError):
        return jsonify(error="Tipologia non valida"), 400
    where_sql, params = inventory_search_where(q)
    with db() as conn:
        t = conn.execute(
            "SELECT subgroup_field_id FROM item_types WHERE id=?", (type_id,)
        ).fetchone()
        if not t or not t["subgroup_field_id"]:
            return jsonify(subgroups=[], enabled=False)
        fid = int(t["subgroup_field_id"])
        f = conn.execute(
            "SELECT label FROM type_fields WHERE id=? AND type_id=? AND active=1", (fid,type_id)
        ).fetchone()
        if not f:
            return jsonify(subgroups=[], enabled=False)
        where_sql = append_inventory_condition(where_sql, "i.item_type_id=?")
        all_params = [*params, type_id, fid]
        sql = """
            SELECT CASE WHEN TRIM(COALESCE(cv.value,''))='' THEN '__none__' ELSE TRIM(cv.value) END AS subgroup_key,
                   CASE WHEN TRIM(COALESCE(cv.value,''))='' THEN 'Senza valore' ELSE TRIM(cv.value) END AS label,
                   COUNT(*) AS item_count
            FROM items i
            LEFT JOIN item_custom_values cv ON cv.item_id=i.id AND cv.field_id=?
        """ + where_sql + """
            GROUP BY CASE WHEN TRIM(COALESCE(cv.value,''))='' THEN '__none__' ELSE TRIM(cv.value) END
            ORDER BY label COLLATE NOCASE
        """
        # JOIN placeholder precedes WHERE placeholders.
        query_params=[fid,*params,type_id]
        rows=[dict(r) for r in conn.execute(sql,query_params)]
        return jsonify(subgroups=rows, enabled=True, field_id=fid, field_label=f["label"],
                       matched_count=sum(int(x["item_count"]) for x in rows), page_size=50)


@app.get("/api/inventory-subgroup-items")
def api_inventory_subgroup_items():
    q=request.args.get("q","").strip()
    subgroup_key=request.args.get("subgroup_key","").strip()
    try:
        type_id=int(request.args.get("type_id","0")); offset=max(0,int(request.args.get("offset","0")))
    except (TypeError,ValueError):
        return jsonify(error="Parametri non validi"),400
    page_size=50
    where_sql,params=inventory_search_where(q)
    with db() as conn:
        t=conn.execute("SELECT subgroup_field_id FROM item_types WHERE id=?",(type_id,)).fetchone()
        if not t or not t["subgroup_field_id"]: return jsonify(error="Sottogruppo non configurato"),400
        fid=int(t["subgroup_field_id"])
        where_sql=append_inventory_condition(where_sql,"i.item_type_id=?")
        params=[*params,type_id]
        if subgroup_key=='__none__':
            where_sql=append_inventory_condition(where_sql,"TRIM(COALESCE(cv.value,''))=''")
            extra=[]
        else:
            where_sql=append_inventory_condition(where_sql,"TRIM(COALESCE(cv.value,''))=?")
            extra=[subgroup_key]
        base=" FROM items i LEFT JOIN item_custom_values cv ON cv.item_id=i.id AND cv.field_id=? "
        all_params=[fid,*params,*extra]
        total=conn.execute("SELECT COUNT(*)"+base+where_sql,all_params).fetchone()[0]
        sql=(
            """SELECT i.*, t.name AS type_name, t.icon AS type_icon
            """
            + inventory_sort_select_sql()
            + """
                 FROM items i
                 LEFT JOIN item_types t ON t.id=i.item_type_id
                 LEFT JOIN item_custom_values cv ON cv.item_id=i.id AND cv.field_id=?
              """
            + where_sql
            + inventory_order_sql()
            + " LIMIT ? OFFSET ?"
        )
        rows=conn.execute(sql,[*all_params,page_size,offset])
        items=hydrate_inventory_items(conn,rows); nxt=offset+len(items)
        return jsonify(items=items,total=total,offset=offset,next_offset=nxt,page_size=page_size,has_more=nxt<total)


@app.get("/api/inventory-items")
def api_inventory_items():
    q = request.args.get("q", "").strip()
    grouping = request.args.get("group_by", "type").strip().lower()
    group_key = request.args.get("group_key", "").strip()
    if grouping not in {"type", "environment", "none"}:
        grouping = "type"
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except (TypeError, ValueError):
        offset = 0
    # v2: dimensione pagina fissa per evitare liste enormi sul browser.
    page_size = 50

    where_sql, params = inventory_search_where(q)
    condition = ""
    extra = []
    if grouping == "type":
        if group_key == "none":
            condition = "i.item_type_id IS NULL"
        else:
            try:
                type_id = int(group_key)
            except (TypeError, ValueError):
                return jsonify(error="Gruppo tipologia non valido"), 400
            condition = "i.item_type_id=?"
            extra.append(type_id)
    elif grouping == "environment":
        if group_key == "__none__":
            condition = "TRIM(COALESCE(i.environment,''))=''"
        else:
            condition = "TRIM(COALESCE(i.environment,''))=?"
            extra.append(group_key)

    where_sql = append_inventory_condition(where_sql, condition)
    all_params = [*params, *extra]

    with db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM items i" + where_sql,
            all_params,
        ).fetchone()[0]
        sql = (
            """
            SELECT i.*, t.name AS type_name, t.icon AS type_icon
            """
            + inventory_sort_select_sql()
            + """
            FROM items i
            LEFT JOIN item_types t ON t.id=i.item_type_id
            """
            + where_sql
            + inventory_order_sql()
            + " LIMIT ? OFFSET ?"
        )
        rows = conn.execute(sql, [*all_params, page_size, offset])
        items = hydrate_inventory_items(conn, rows)
        next_offset = offset + len(items)
        return jsonify(
            items=items,
            total=total,
            offset=offset,
            next_offset=next_offset,
            page_size=page_size,
            has_more=next_offset < total,
        )


@app.get("/api/items/<int:item_id>")
def api_get_item(item_id):
    with db() as conn:
        row = conn.execute(
            """SELECT i.*, t.name AS type_name, t.icon AS type_icon
               FROM items i LEFT JOIN item_types t ON t.id=i.item_type_id
               WHERE i.id=?""",
            (item_id,),
        ).fetchone()
        if not row:
            return jsonify(error="Elemento non trovato"), 404
        items = hydrate_inventory_items(conn, [row])
        return jsonify(items[0])


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

