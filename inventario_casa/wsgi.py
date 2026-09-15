"""WSGI entry point for Inventario Casa.

Keeps the application module unchanged while applying the Home Assistant
Ingress theme compatibility layer to the rendered page.
"""

import app as inventory


THEME_TEXT_CSS = r"""

/* v2.3.4 - testi e controlli collegati dinamicamente al tema Home Assistant */
html.ha-theme-linked {
  color-scheme: normal !important;
  --inv-ha-text: var(--primary-text-color, var(--inv-text));
  --inv-ha-muted: var(--secondary-text-color, var(--inv-muted));
  --inv-ha-divider: var(--divider-color, var(--inv-border));
  --inv-ha-field: var(--input-fill-color, var(--secondary-background-color, #0f1318));
}

html.ha-theme-linked body,
html.ha-theme-linked h1,
html.ha-theme-linked h2,
html.ha-theme-linked label,
html.ha-theme-linked .itemname,
html.ha-theme-linked .typename,
html.ha-theme-linked .item-group-title,
html.ha-theme-linked .item-subgroup-title,
html.ha-theme-linked .item-preview-value,
html.ha-theme-linked .barcode-status,
html.ha-theme-linked #backupDlg .backup-row-name,
html.ha-theme-linked #backupDlg .backup-info,
html.ha-theme-linked #backupDlg .backup-list-head {
  color: var(--inv-ha-text) !important;
}

html.ha-theme-linked .sub,
html.ha-theme-linked .meta,
html.ha-theme-linked .hint,
html.ha-theme-linked .muted,
html.ha-theme-linked .items-group-wrap,
html.ha-theme-linked .items-limit-wrap,
html.ha-theme-linked .items-page-size,
html.ha-theme-linked .items-list-info,
html.ha-theme-linked .inventory-loader,
html.ha-theme-linked .item-group-count,
html.ha-theme-linked .item-group-arrow,
html.ha-theme-linked .item-subgroup-arrow,
html.ha-theme-linked .typecount,
html.ha-theme-linked .item-preview-label,
html.ha-theme-linked .item-preview-photo-title,
html.ha-theme-linked .item-preview-photo-label,
html.ha-theme-linked .item-preview-photo-more,
html.ha-theme-linked #backupDlg .backup-row-meta,
html.ha-theme-linked #backupDlg .backup-create-btn small {
  color: var(--inv-ha-muted) !important;
}

html.ha-theme-linked input,
html.ha-theme-linked select,
html.ha-theme-linked textarea {
  background: var(--inv-ha-field) !important;
  color: var(--inv-ha-text) !important;
  caret-color: var(--inv-ha-text) !important;
  border-color: var(--inv-ha-divider) !important;
}

html.ha-theme-linked input::placeholder,
html.ha-theme-linked textarea::placeholder {
  color: var(--inv-ha-muted) !important;
  opacity: .9 !important;
}

html.ha-theme-linked select option {
  background: var(--secondary-background-color, var(--inv-ha-field)) !important;
  color: var(--inv-ha-text) !important;
}

html.ha-theme-linked button.secondary,
html.ha-theme-linked .tabbtn,
html.ha-theme-linked .micbtn,
html.ha-theme-linked .types-add-top,
html.ha-theme-linked .type-add,
html.ha-theme-linked .new-item-head,
html.ha-theme-linked .custom-field-title,
html.ha-theme-linked .item-row,
html.ha-theme-linked .item-group-head,
html.ha-theme-linked .item-subgroup-head,
html.ha-theme-linked .item-preview-no-photo,
html.ha-theme-linked .search-clear {
  color: var(--inv-ha-text) !important;
}

html.ha-theme-linked .custom-field-accordion,
html.ha-theme-linked .item-group,
html.ha-theme-linked .item-subgroup,
html.ha-theme-linked .item-preview-row {
  border-color: color-mix(in srgb, var(--inv-ha-divider) 80%, var(--inv-ha-text) 20%) !important;
}

/* Mantiene leggibili i sottogruppi aperti anche con temi HA chiari. */
html.ha-theme-linked .item-subgroup:not(.collapsed) > .item-subgroup-head,
html.ha-theme-linked .item-subgroup:not(.collapsed) > .item-subgroup-head .item-group-count {
  color: var(--inv-ha-text) !important;
}

/* I colori semantici (successo, errore, pericolo e accenti) restano intenzionalmente invariati. */
"""


THEME_LAYOUT_CSS = r"""

/* v2.3.4 - maggiore separazione visiva con temi Home Assistant chiari */
html.ha-theme-linked {
  --inv-ha-card: var(
    --card-background-color,
    var(--secondary-background-color, var(--primary-background-color))
  );
}

/* Card principali: maggiore separazione dallo sfondo della pagina */
html.ha-theme-linked .stat,
html.ha-theme-linked .panel,
html.ha-theme-linked .type-card {
  background: var(--inv-ha-card) !important;
  border-color:
    color-mix(
      in srgb,
      var(--divider-color, var(--primary-text-color)) 75%,
      transparent
    ) !important;
  box-shadow:
    0 2px 8px
    color-mix(
      in srgb,
      var(--primary-text-color) 9%,
      transparent
    ) !important;
}

/* Contenitori interni: distinguibili senza creare riquadri pesanti */
html.ha-theme-linked .item,
html.ha-theme-linked .type-row,
html.ha-theme-linked .fieldrow {
  background:
    color-mix(
      in srgb,
      var(--secondary-background-color, var(--inv-ha-card)) 92%,
      transparent
    ) !important;
}

/* Riquadro informativo della scheda Foto */
html.ha-theme-linked .new-item-photo-hint,
html.ha-theme-linked .photo-hint {
  background: var(--secondary-background-color, var(--inv-ha-card)) !important;
  color: var(--secondary-text-color, var(--inv-ha-muted)) !important;
  border-color: var(--divider-color, var(--inv-ha-divider)) !important;
}

"""


# PAGE contiene un unico blocco <style>; inseriamo gli override in coda così
# prevalgono sui colori fissi delle versioni precedenti senza cambiare markup/API.
if THEME_TEXT_CSS not in inventory.PAGE:
    inventory.PAGE = inventory.PAGE.replace("</style>", THEME_TEXT_CSS + "\n</style>", 1)

if THEME_LAYOUT_CSS not in inventory.PAGE:
    inventory.PAGE = inventory.PAGE.replace("</style>", THEME_LAYOUT_CSS + "\n</style>", 1)

app = inventory.app

# v2.3.5 - compatibilità menu SELECT nativi Windows/Chrome
SELECT_NATIVE_FIX_CSS = r"""
<style>
/*
 * I menu OPTION sono controlli nativi del browser/OS.
 * Su Windows/Chrome possono avere sfondo bianco anche con tema HA scuro.
 */
select option {
  background: #ffffff !important;
  color: #202124 !important;
}

select option:checked {
  background: #8ab4f8 !important;
  color: #202124 !important;
}
</style>
"""

if SELECT_NATIVE_FIX_CSS not in inventory.PAGE:
    inventory.PAGE = inventory.PAGE.replace(
        "</head>",
        SELECT_NATIVE_FIX_CSS + "\n</head>",
        1
    )
