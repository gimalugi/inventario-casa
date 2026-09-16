# Inventario Casa v2.3.6

🇮🇹 [Italiano](README.md) | 🇬🇧 **English**

Inventario Casa is a Home Assistant App designed to manage a personal home inventory.

It allows you to catalog objects, books, comics and other belongings, organizing them by type, room and location, with photos and customizable fields.

> **Language:** The current Inventario Casa user interface is available in Italian. English localization may be added in a future release.

## Installation

Inventario Casa can be installed through the Home Assistant App Store.

1. Open **Home Assistant**.
2. Go to **Settings → Apps → App Store**.
3. Open the **⋮ → Repositories** menu.
4. Add the repository: `https://github.com/gimalugi/inventario-casa`.
5. Return to the App Store.
6. Select **Inventario Casa**.
7. Click **Install**.
8. When installation is complete, start the App.

There is no need to manually copy files into the `/addons` directory.

## Updating

When a new version is published, Home Assistant can notify you that an update is available from the App page.

Updates are performed directly through Home Assistant without manually replacing the App files.

Do not delete the App data when updating.

## Main Features

- Home inventory management.
- Customizable item types.
- Custom fields for each item type.
- Organization by room and location.
- Object photos.
- Global database search.
- Grouping by item type or room.
- Collapsible groups.
- Progressive loading for large inventories.
- Responsive interface optimized for smartphones.
- Dynamic integration with Home Assistant themes.
- Voice dictation for compatible text fields.
- ISBN/EAN support for books and comics.
- Google Books lookup with Open Library fallback.
- Barcode scanning using the device camera over HTTPS.

## Books and Comics

Books and comics can use ISBN/EAN codes.

Available features include:

- manual ISBN/EAN entry;
- on-demand metadata lookup;
- Google Books as the primary metadata source;
- automatic fallback to Open Library;
- preview before applying retrieved information;
- automatic completion of empty fields only;
- ISBN/EAN barcode scanning using the camera.

Manual ISBN/EAN entry always remains available.

## Camera and HTTPS

Starting with version 2.3.5, features requiring camera access are enabled only when the browser is running in a secure HTTPS context.

With HTTPS:

- live barcode scanning is used when supported by the browser;
- if live scanning is unavailable, photo-based scanning can be used as a fallback.

With HTTP:

- the barcode scan button remains visible but is disabled;
- the camera is not activated;
- ISBN/EAN codes can still be entered manually;
- metadata lookup remains available.

No camera scanning is performed in the background.

## Home Assistant Themes

Inventario Casa dynamically uses colors from the active Home Assistant theme.

The interface adapts elements including:

- backgrounds;
- cards and panels;
- primary and secondary text;
- input fields;
- menus;
- placeholders;
- borders and separators.

Both light and dark Home Assistant themes are supported.

## Large Inventories

Inventario Casa is designed to handle large collections efficiently.

Features include:

- item counts calculated directly from SQLite;
- progressive loading;
- up to 50 items loaded per request;
- **Load more** functionality;
- global search including custom fields;
- groups initially collapsed to avoid unnecessary loading;
- individual item retrieval directly from the database.

## Data Persistence

App data is stored separately from the application code:

- Database: `/data/inventario_casa/inventario.db`
- Photos: `/media/inventario_casa/oggetti`

Updates preserve the database, photos, inventory items and existing custom fields.

## Version 2.3.5

Main changes:

- camera-based ISBN/EAN scanning is available only over HTTPS;
- barcode scanning is disabled on insecure HTTP connections;
- manual ISBN/EAN entry and metadata lookup remain available;
- live camera scanning is used when supported;
- photo-based fallback remains available in secure contexts;
- improved native dropdown readability on Windows/Chrome;
- improved Home Assistant light and dark theme integration;
- no database or schema changes.

## Data Safety

Inventario Casa updates are designed to preserve:

- the database;
- photos;
- item types;
- custom fields;
- inventory items.

A recent Home Assistant backup is recommended before major structural changes.

## Version 2.3.6

- Fixed the default item types created on new installations.
- New installations start with **Apparecchiature elettroniche**, **Libri** and **Oggetti**.
- The **Libri** type includes Author, ISBN, Publisher and Year fields.
- Default types and fields are created only during the first initialization.
- Types deleted by the user are no longer recreated after restarting the App.
- No automatic changes are made to existing item types or inventory data.
