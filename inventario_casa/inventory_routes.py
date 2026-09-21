from flask import Blueprint, jsonify, request


def create_inventory_blueprint(*, db):
    bp = Blueprint("inventory", __name__)

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


    @bp.get("/api/bootstrap")
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
            return " WHERE (" + where_sql[7:] + ") AND " + condition
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


    def inventory_page_size():
        try:
            value = int(request.args.get("page_size", "50"))
        except (TypeError, ValueError):
            value = 50

        return value if value in (10, 50, 100) else 50


    @bp.get("/api/inventory-groups")
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
                return jsonify(groups=groups, matched_count=count, page_size=inventory_page_size())

            groups = [dict(r) for r in conn.execute(sql, params)]
            matched_count = sum(int(g["item_count"]) for g in groups)
            return jsonify(groups=groups, matched_count=matched_count, page_size=inventory_page_size())


    @bp.get("/api/inventory-subgroups")
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
                           matched_count=sum(int(x["item_count"]) for x in rows), page_size=inventory_page_size())


    @bp.get("/api/inventory-subgroup-items")
    def api_inventory_subgroup_items():
        q=request.args.get("q","").strip()
        subgroup_key=request.args.get("subgroup_key","").strip()
        try:
            type_id=int(request.args.get("type_id","0")); offset=max(0,int(request.args.get("offset","0")))
        except (TypeError,ValueError):
            return jsonify(error="Parametri non validi"),400
        page_size=inventory_page_size()
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


    @bp.get("/api/inventory-items")
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
        page_size = inventory_page_size()

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


    @bp.get("/api/items/<int:item_id>")
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

    return bp
