# 🏠 Inventario Casa v2.5.4

🇮🇹 [Italiano](README.md) | 🇬🇧 **English**

**Inventario Casa** is a Home Assistant App designed to catalog what you own and quickly find **what you have and where it is located**.

It is suitable both for everyday household objects and for collections such as books, comics, magazines, video games, VHS tapes and other custom categories.

## 📦 Main features

### Item cataloging

For each item you can store the main information, location, specific details, notes and photographs.

### 📍 Detailed location

Items can be located using:

- Room
- Furniture or shelf
- Shelf level or drawer
- Container
- Container code

### 🏷️ Customizable types

The inventory uses a single global database, while items can belong to different types.

Predefined types are available and you can freely create new types for any kind of collection.

### 🧩 Custom fields

Each type can have its own fields:

- Text
- Number
- Date
- Long text
- Select list
- Checkbox

Fields can be required or optional, reordered and enabled/disabled.

### 🔎 Global search

Search can find items using both the main information and custom fields.

The **×** button clears the search text and immediately restores the complete inventory.

### 🗂️ Groups and subgroups

Items can be displayed grouped by type and, when configured, further divided into subgroups.

For example:

**Comics → Series → items**

Pagination keeps the interface responsive even with large inventories.

### 🔢 Natural numeric sorting

Collections using a **Number** field are sorted numerically, avoiding alphabetical orders such as `1, 10, 11, 2`.

A **Number suffix** is also supported.

### 📷 Photographs

Each item can have multiple photographs.

Images are automatically processed and optimized and can be opened using the enlarged image viewer.

### 📚 ISBN and barcodes

For books and other compatible items, ISBN and barcode information can be used.

Camera scanning is available when the browser and connection support it. Manual entry is always available.

### 🎙️ Voice dictation

Compatible browsers can provide voice dictation for text fields.

## 🧭 Interface

Starting with version **2.5.2**, the interface includes a new navigation sidebar with dedicated sections for:

- Inventory
- New item
- Types
- Backup
- Settings

Language selection is available in the **Settings** page.

The interface is responsive and adapts to desktop, tablet and smartphone screens.

## 🎨 Home Assistant integration

When Inventario Casa is opened through **Ingress**, the interface dynamically uses the colors and background of the currently selected Home Assistant theme.

If theme information is unavailable, Inventario Casa automatically uses its default graphical theme.

Theme synchronization only takes place when necessary: the App does not use polling or periodic theme monitoring.

## 💾 Data storage

The inventory database is stored at:

`/data/inventario_casa/inventario.db`

Photographs are stored separately at:

`/media/inventario_casa/oggetti/`

Database backups are stored at:

`/media/inventario_casa/db_backups/`

This separation keeps photographs and backups outside the App's internal data and allows them to be backed up separately.

## 💾 Backup & Recovery

Since version 2.3.0, Inventario Casa provides database backup management directly from the interface.

You can:

- create manual backups;
- check date, size and integrity;
- download backups;
- restore a backup;
- automatically create a copy of the current database before a restore.

The selected backup is checked using `PRAGMA integrity_check` before the restore, and the resulting database is checked again afterwards.

### Recovery Mode

If database initialization or a migration prevents normal startup, the App's web server remains available in Recovery Mode.

The Recovery screen allows available backups to be viewed, downloaded and restored without using Docker, SQLite or the Home Assistant CLI.

## 🔐 Database security and migrations

The SQLite schema version is stored in the technical `app_meta` table.

When an update requires a new schema version, a consistent SQLite backup is automatically created before the migration.

The backup is checked using `PRAGMA integrity_check`. If the check does not return `ok`, the migration is stopped.

When the schema is already up to date, a normal App restart does not create additional backups.

## ⚙️ How it works

Inventario Casa is a passive App.

It does not use:

- schedulers;
- cron;
- continuous scans;
- periodic polling;
- background monitoring processes.

Operations are performed when requested by the user.

## 📋 Version history

### 2.5.4 — Reopening item types and search

- Fixed item type groups appearing empty when reopened with items or subgroups already loaded.
- Reloaded the unfiltered inventory when navigation clears the global search.
- No database schema changes.

### 2.5.3 — Interface, search and pagination

- New compact header optimized for desktop and mobile.
- Improved global search and navigation between views.
- Fixed search results being displayed under incorrect item types.
- Configurable pagination in Settings: 10, 50 or 100 items.
- Improved contextual Inventory statistics.
- Fixed the "Property" field display in item details.
- Improved responsive layout on smartphones.
- No database schema changes.

### 2.5.2 — Sidebar and Settings

- New navigation sidebar.
- Dedicated views for Inventory, New item, Types and Backup.
- New Settings page.
- Language selection moved to Settings.
- Updated Italian/English translations.
- Improved responsive layout.
- Search field and search button aligned.
- No database schema changes.

### 2.5.0 — Architectural reorganization

- Reorganized the internal application architecture.
- Frontend, CSS and JavaScript separated.
- APIs split into dedicated modules.
- Database, migrations and Backup & Restore management separated.
- Backup retention configuration added.
- Multilingual management consolidated.
- Frontend asset caching improved.
- Recovery page separated from the main backend.
- Restore procedure issues corrected.
- Compatibility with existing database, schema and data maintained.

### 2.4.x — Multilingual interface

- Full Italian/English interface support.
- Manual language selector with saved preference.
- Automatic Home Assistant language detection.
- Localization of inventory, types, search, groups, pagination and Backup & Restore.
- Recovery interface available in Italian and English.
- Improved photograph and thumbnail management.
- Improved asynchronous loading of groups and subgroups.

### 2.3.x — Backup, Recovery and camera

- Complete SQLite backup management.
- Manual backups, downloads and guided restore.
- Integrity checks before and after restore.
- Automatic backup before restore.
- Recovery Mode.
- Backup interface improvements.
- Improved camera compatibility with HTTPS.
- Photograph fallback retained.
- Improved Home Assistant theme integration.
- Default types are created only during the first database initialization.

### 2.2.x — Home Assistant theme and migrations

- Dynamic Home Assistant theme through Ingress.
- Fallback to the default graphical theme.
- Internal SQLite schema version.
- Technical `app_meta` table.
- Automatic backups before schema migrations.
- `PRAGMA integrity_check` validation.
- Mobile interface improvements.
- Improved dialogs and search controls.

### 2.1.x — Collections and large inventories

- Configurable subgroups for types.
- Real pagination for groups and subgroups.
- Optimization for very large collections.
- Natural numeric sorting.
- Number suffix support.
- Item previews with photographs.
- Compact read-only item details dialog.

### 2.0.0

Foundation of the 2.x generation of the application.

### 0.1.x

The initial versions progressively introduced cataloging, types, locations, photographs, search, custom fields and ISBN/barcode scanning.

The complete detailed history is available in the [CHANGELOG](inventario_casa/CHANGELOG.md).

## 📚 Documentation

- [Complete documentation](inventario_casa/DOCS.md)
- [CHANGELOG](inventario_casa/CHANGELOG.md)
- [Regression checklist](inventario_casa/REGRESSION_CHECKLIST.md)
- [GitHub Releases](https://github.com/gimalugi/inventario-casa/releases)

---

**Inventario Casa** — your home inventory directly in Home Assistant.
