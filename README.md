# 🏠 Inventario Casa v2.5.4

🇮🇹 **Italiano** | 🇬🇧 [English](README_EN.md)

**Inventario Casa** è un'App per Home Assistant pensata per catalogare ciò che possiedi e sapere rapidamente **che cosa hai e dove si trova**.

È adatta sia agli oggetti di uso quotidiano sia a collezioni come libri, fumetti, riviste, videogiochi, videocassette e altre categorie personalizzate.

## 📦 Funzioni principali

### Catalogazione degli oggetti

Per ogni elemento puoi memorizzare le informazioni principali, la posizione, eventuali dettagli specifici, note e fotografie.

### 📍 Posizione dettagliata

Gli oggetti possono essere localizzati indicando:

- Ambiente
- Mobile o scaffale
- Ripiano o cassetto
- Contenitore
- Codice del contenitore

### 🏷️ Tipologie personalizzabili

L'inventario utilizza un unico archivio globale, ma gli elementi possono appartenere a tipologie differenti.

Sono disponibili tipologie predefinite ed è possibile crearne liberamente di nuove.

### 🧩 Campi personalizzati

Ogni tipologia può avere campi propri:

- Testo
- Numero
- Data
- Testo esteso
- Selezione da elenco
- Casella di controllo

I campi possono essere obbligatori o facoltativi, ordinati e attivati/disattivati.

### 🔎 Ricerca globale

La ricerca permette di trovare rapidamente gli elementi utilizzando sia i dati principali sia i campi personalizzati.

Il pulsante **×** cancella il testo e ripristina immediatamente l'inventario completo.

### 🗂️ Raggruppamenti e sottogruppi

Gli elementi possono essere visualizzati raggruppati per tipologia e, quando configurato, ulteriormente suddivisi in sottogruppi.

Ad esempio, i fumetti possono essere raggruppati per **Serie**.

La paginazione mantiene l'interfaccia veloce anche con inventari numerosi.

### 🔢 Ordinamento numerico naturale

Le raccolte che utilizzano un campo **Numero** vengono ordinate numericamente in modo naturale, evitando ordinamenti come `1, 10, 11, 2`.

È supportato anche il campo **Suffisso numero**.

### 📷 Fotografie

Ogni elemento può avere più fotografie.

Le immagini vengono elaborate e ottimizzate automaticamente e possono essere aperte tramite visualizzazione ingrandita.

### 📚 ISBN e codici a barre

Per libri e altri elementi compatibili è possibile utilizzare ISBN o codici a barre.

La lettura può utilizzare la fotocamera quando il browser e la connessione lo consentono; l'inserimento manuale rimane sempre disponibile.

### 🎙️ Dettatura vocale

Nei browser compatibili è disponibile la dettatura vocale per velocizzare la compilazione dei campi testuali.

## 🧭 Interfaccia

Dalla versione **2.5.2** è disponibile una nuova sidebar di navigazione con sezioni dedicate a:

- Inventario
- Nuovo elemento
- Tipologie
- Backup
- Impostazioni

La selezione della lingua è disponibile nella pagina **Impostazioni**.

L'interfaccia è responsive e si adatta a desktop, tablet e smartphone.

## 🎨 Integrazione con Home Assistant

Quando Inventario Casa viene aperto tramite **Ingress**, l'interfaccia utilizza dinamicamente i colori e lo sfondo del tema Home Assistant attualmente selezionato.

Se le informazioni del tema non sono disponibili, viene utilizzata automaticamente la grafica predefinita di Inventario Casa.

La sincronizzazione del tema avviene solo quando necessario: l'app non utilizza polling o attività periodiche per il tema.

## 💾 Dove vengono salvati i dati

Il database dell'inventario è memorizzato in:

`/data/inventario_casa/inventario.db`

Le fotografie sono memorizzate separatamente in:

`/media/inventario_casa/oggetti/`

I backup del database sono memorizzati in:

`/media/inventario_casa/db_backups/`

La separazione consente di mantenere le fotografie e i backup fuori dai dati interni dell'app e di gestirne il backup separatamente.

## 🔄 Aggiornamenti

Gli aggiornamenti dell'app sono progettati per conservare il database e gli elementi già catalogati.

Non è necessario cancellare i dati dell'app durante un normale aggiornamento.

Prima di operazioni straordinarie o migrazioni è comunque consigliato conservare una copia di sicurezza del database.

## 💾 Backup & Recovery

Dalla versione 2.3.0 Inventario Casa dispone di una gestione dei backup direttamente dall'interfaccia.

È possibile:

- creare manualmente un backup;
- controllarne data, dimensione e integrità;
- scaricarlo;
- ripristinarlo;
- creare automaticamente una copia del database corrente prima del restore.

Il backup selezionato viene verificato con `PRAGMA integrity_check` prima del restore e anche il database risultante viene verificato dopo il ripristino.

### Modalità Recovery

Se l'inizializzazione del database o una migrazione impediscono il normale avvio, il server web dell'app rimane disponibile in modalità Recovery.

La schermata Recovery permette di vedere, scaricare e ripristinare i backup disponibili senza usare Docker, SQLite o la CLI di Home Assistant.

## 🔐 Sicurezza database e migrazioni

La versione dello schema SQLite viene registrata nella tabella tecnica `app_meta`.

Quando un aggiornamento richiede una nuova versione dello schema, prima della migrazione viene creato automaticamente un backup SQLite consistente.

Il backup viene controllato con `PRAGMA integrity_check`. Se il controllo non restituisce `ok`, la migrazione viene interrotta.

Quando lo schema è già aggiornato, un normale riavvio dell'app non crea nuovi backup.

## ⚙️ Funzionamento

Inventario Casa è un'app passiva.

Non utilizza:

- scheduler;
- cron;
- scansioni continue;
- polling periodico;
- processi di monitoraggio in background.

Le operazioni vengono eseguite quando richieste dall'utente.

## 📋 Cronologia delle versioni

### 2.5.4 — Riapertura tipologie e ricerca

- Corretta la riapertura delle tipologie con elementi o sottogruppi già caricati che potevano apparire vuote.
- Ripristinato l'inventario senza filtri quando la navigazione cancella la ricerca globale.
- Nessuna modifica allo schema del database.

### 2.5.3 — Interfaccia, ricerca e paginazione

- Nuovo header compatto e ottimizzato per desktop e mobile.
- Migliorata la ricerca globale e la navigazione tra le viste.
- Corretta la suddivisione dei risultati di ricerca per tipologia.
- Paginazione configurabile dalle Impostazioni: 10, 50 o 100 elementi.
- Migliorate le statistiche contestuali dell'Inventario.
- Corretta la visualizzazione del campo "Luogo" nel dettaglio degli elementi.
- Migliorata la resa responsive su smartphone.
- Nessuna modifica allo schema del database.

### 2.5.2 — Sidebar e Impostazioni

- Nuova sidebar di navigazione.
- Viste dedicate per Inventario, Nuovo elemento, Tipologie e Backup.
- Nuova pagina Impostazioni.
- Selezione della lingua spostata nelle Impostazioni.
- Aggiornate le traduzioni Italiano/Inglese.
- Migliorato il layout responsive.
- Allineati campo di ricerca e pulsante lente.
- Nessuna modifica allo schema del database.

### 2.5.0 — Riorganizzazione architetturale

- Riorganizzata l'architettura interna dell'applicazione.
- Separati frontend, CSS e JavaScript.
- Suddivise le API in moduli dedicati.
- Separata la gestione del database, delle migrazioni e di Backup & Restore.
- Aggiunta la configurazione della retention dei backup.
- Consolidata la gestione multilingua.
- Migliorata la gestione della cache degli asset frontend.
- Separata la pagina Recovery.
- Corretti problemi nella procedura di ripristino.
- Mantenuta la compatibilità con database, schema e dati esistenti.

### 2.4.x — Multilingua e interfaccia

- Supporto completo Italiano/Inglese.
- Selettore manuale della lingua con memorizzazione della preferenza.
- Rilevamento automatico della lingua di Home Assistant.
- Localizzazione di inventario, tipologie, ricerca, gruppi, paginazione e Backup & Restore.
- Recovery disponibile in Italiano e Inglese.
- Miglioramenti alla gestione delle fotografie e delle miniature.
- Miglioramenti al caricamento asincrono di gruppi e sottogruppi.

### 2.3.x — Backup, Recovery e fotocamera

- Introdotta la gestione completa dei backup SQLite.
- Backup manuali, download e ripristino guidato.
- Verifica dell'integrità prima e dopo il ripristino.
- Backup automatico prima del restore.
- Modalità Recovery.
- Miglioramenti grafici della pagina Backup.
- Migliorata la compatibilità della fotocamera con HTTPS.
- Mantenuto il fallback tramite acquisizione fotografica.
- Migliorata l'integrazione grafica con il tema Home Assistant.
- Le tipologie predefinite vengono create solo alla prima inizializzazione del database.

### 2.2.x — Tema Home Assistant e migrazioni

- Tema grafico collegato dinamicamente ai colori di Home Assistant tramite Ingress.
- Fallback alla grafica predefinita.
- Versione interna dello schema SQLite.
- Tabella tecnica `app_meta`.
- Backup automatico prima delle migrazioni.
- Verifica tramite `PRAGMA integrity_check`.
- Miglioramenti dell'interfaccia mobile.
- Miglioramenti alla gestione delle finestre e della ricerca.

### 2.1.x — Raccolte e grandi archivi

- Sottogruppi configurabili per tipologia.
- Paginazione reale per gruppi e sottogruppi.
- Ottimizzazione per raccolte molto grandi.
- Ordinamento numerico naturale.
- Supporto al Suffisso numero.
- Anteprime degli elementi con fotografie.
- Modale compatta di sola lettura.

### 2.0.0

Base della generazione 2.x dell'applicazione.

### 0.1.x

Le versioni iniziali hanno introdotto progressivamente catalogazione, tipologie, posizioni, fotografie, ricerca, campi personalizzati e scansione ISBN/EAN.

La cronologia completa e dettagliata è disponibile nel [CHANGELOG](inventario_casa/CHANGELOG.md).

## 📚 Documentazione

- [Documentazione completa](inventario_casa/DOCS.md)
- [CHANGELOG](inventario_casa/CHANGELOG.md)
- [Checklist di regressione](inventario_casa/REGRESSION_CHECKLIST.md)
- [Release GitHub](https://github.com/gimalugi/inventario-casa/releases)

---

**Inventario Casa** — il tuo inventario domestico direttamente in Home Assistant.
