# REGRESSION_CHECKLIST.md

Da verificare prima di ogni rilascio di Inventario Casa:

- [x] Inserimento nuovo elemento
- [x] Modifica elemento
- [x] Eliminazione elemento
- [x] Schede: Generale / Dettagli / Posizione / Foto / Note
- [x] Campi custom per tipologia
- [x] Modifica tipologie esistenti
- [x] Aggiunta campi
- [x] Rinomina campi
- [x] Riordino campi con frecce su/giù
- [x] Campo obbligatorio/facoltativo
- [x] Nascondi/Riattiva campo senza cancellare dati
- [x] Ricerca globale
- [x] Posizione: Ambiente / Mobile-Scaffale / Ripiano-Cassetto / Contenitore
- [x] Suggerimenti automatici delle posizioni già usate
- [x] Foto multiple
- [x] Profilo foto automatico / Standard / Fumetti-collezionabili
- [x] Foto salvate in /media/inventario_casa/oggetti
- [x] Miniature e apertura foto grande
- [x] Compatibilità con database precedente
- [x] Migrazioni additive senza perdita dati
- [x] Fumetto: Serie / Numero / Editore / Anno / Condizione / Difetti
- [x] Layout desktop e mobile
- [x] Testo di esempio/placeholder facoltativo per i campi personalizzati

- [x] Smartphone: nessun overflow orizzontale previsto
- [x] Smartphone: dialog modifica a tutto schermo
- [x] Smartphone: form a una colonna
- [x] Smartphone: tab scorrevoli e touch target adeguati
- [x] Smartphone: lista elementi con azioni non compresse

- [x] Smartphone: contrasto campi migliorato
- [x] Smartphone: placeholder leggibili
- [x] Dettatura vocale: Nome / Descrizione / Note / Tag
- [x] Dettatura vocale: campi personalizzati Testo / Testo lungo
- [x] Dettatura vocale: fallback browser non compatibile

- [x] Migrazione database legacy: item_photos.caption -> item_photos.label
- [x] Bootstrap con database proveniente dalle versioni precedenti

## Controlli v0.1.11
- [x] Elenco tipologie compatto
- [x] Ricerca tipologie
- [x] Apertura editor cliccando una tipologia
- [x] Riduzione/espansione pannello con stato persistente nel browser
- [x] Eliminazione tipologia non utilizzata
- [x] Blocco eliminazione tipologia utilizzata da elementi
- [x] Nessuna modifica distruttiva ai dati esistenti
- [x] Layout smartphone preservato

- [x] Apertura foto dentro Ingress senza nuova scheda / senza 401 su mobile
- [x] Nessun polling, scheduler o job aggiuntivo in background

- [x] Contrasto mobile: sfondo/pannelli distinguibili dai campi di inserimento

- [x] Versione README coerente con config.yaml (0.1.14)
- [x] Contrasto forte mobile: sfondo/pannelli chiari rispetto ai campi scuri

- [x] Versione README coerente con config.yaml (0.1.15)
- [x] Sfondo mobile blu/viola/rosso distinto dalle card
- [x] Card/pannelli più scuri dello sfondo generale
- [x] Campi input più scuri e con bordo evidente

- [x] Versione README coerente con config.yaml (0.1.16)
- [x] Card chiare trasparenti su desktop e mobile
- [x] Campi input ancora scuri e leggibili
- [x] Nessun job o polling aggiuntivo

- [x] Pulsante nuova tipologia visibile accanto al titolo
- [x] Pulsante nuova tipologia accessibile anche con elenco chiuso
- [x] Vecchio pulsante fondo elenco nascosto

- [x] Bordi colorati pulsanti senza alterare le azioni
- [x] Tab colorati su desktop e mobile
- [x] Pulsanti elemento foto/modifica/elimina distinguibili per colore
- [x] Tipologie con accenti colore senza perdita di leggibilità

- [x] Dettagli: inizialmente visibili solo i titoli dei campi
- [x] Clic sul titolo apre il relativo campo
- [x] Apertura di un campo richiude gli altri
- [x] Valori custom salvati anche quando il pannello è chiuso
- [x] Indicatore ✓ sui campi già compilati

- [x] Campo attivo scorre automaticamente in vista su mobile
- [x] Tastiera virtuale non copre il campo attivo
- [x] Ultimi campi raggiungibili senza scroll manuale aggiuntivo

- [x] Nuovo elemento chiuso di default e apribile al tocco
- [x] Nuovo elemento si richiude dopo il salvataggio
- [x] Lista Cosa possiedo limitabile a 20/50/100
- [x] Limite applicato lato SQLite
- [x] Ricerca compatibile con limite 20/50/100
- [x] Conteggio totale inventario resta corretto

- [x] Editor tipologia mobile: campo nome a tutta larghezza
- [x] Editor tipologia mobile: microfono allineato correttamente
- [x] Editor tipologia mobile: barra salvataggio non copre i campi
- [x] Editor tipologia mobile: pulsanti ordinati e leggibili

- [x] Step barcode 1: Libro conserva ISBN manuale
- [x] Step barcode 1: Fumetto riceve ISBN / EAN senza duplicarlo agli avvii successivi
- [x] Inserimento manuale invariato e sempre disponibile

- [x] Step barcode 2: pulsante Cerca dati presente su ISBN / ISBN-EAN
- [x] Step barcode 2: ricerca solo su richiesta, nessun background job
- [x] Step barcode 2: anteprima e conferma prima dell’applicazione
- [x] Step barcode 2: non sovrascrive campi già compilati
- [x] Inserimento manuale resta sempre disponibile

- [x] Step barcode 3: pulsante scansione presente solo sui campi ISBN/EAN
- [x] Fotocamera attivata solo su richiesta e arrestata alla chiusura
- [x] Lettura da foto disponibile come alternativa
- [x] Codice rilevato non avvia automaticamente la ricerca dati
- [x] Inserimento manuale ISBN/EAN sempre disponibile

- [x] Ricerca ISBN: Google Books fonte primaria
- [x] Ricerca ISBN: fallback Open Library
- [x] Inserimento manuale sempre disponibile

- [x] Scanner mobile: fallback senza BarcodeDetector
- [x] Scanner mobile: fotocamera fermata alla chiusura/rilevamento
- [x] Scanner foto: fallback locale pyzbar/zbar
- [x] Scanner: nessuna scansione in background
- [x] Inserimento manuale barcode sempre disponibile

- [x] Scanner mobile HTTP: apertura diretta fotocamera tramite capture
- [x] Scanner mobile HTTPS: scansione live mantenuta
- [x] Scanner: fallback foto disponibile se getUserMedia fallisce
- [x] Scanner: inserimento manuale sempre disponibile

- [x] Lista elementi compatta a una riga cliccabile
- [x] Apertura scheda elemento dalla lista
- [x] Eliminazione elemento dalla scheda
- [x] Foto ancora accessibili dalla scheda

- [x] Raggruppamento elementi per tipologia
- [x] Raggruppamento elementi per ambiente
- [x] Modalità lista non raggruppata
- [x] Gruppi richiudibili con stato persistente
- [x] Ricerca compatibile con i gruppi

- [x] Layout mobile Cosa possiedo senza sovrapposizioni
- [x] Raggruppa e Mostra affiancati su smartphone
- [x] Nomi gruppi lunghi non rompono il layout

- [x] Bordi sezioni principali più evidenti
- [x] Bordi campi input/select/textarea più evidenti
- [x] Tipologie con bordi distintivi
- [x] Gruppi inventario visivamente separati
- [x] Layout mobile invariato e leggibile

- [x] v2: conteggio gruppi sull’intero database
- [x] v2: massimo 50 elementi caricati per gruppo e richiesta
- [x] v2: Carica altri aggiunge la pagina successiva
- [x] v2: ricerca globale su items e campi personalizzati
- [x] v2: gruppi nuovi chiusi senza caricamento massivo
- [x] v2: apertura scheda elemento anche se non già caricata
- [x] v2: database e foto esistenti invariati


## v2.1.0 - sottogruppi
- [ ] In Modifica tipologia è possibile scegliere un campo attivo come Sottogruppo elenco.
- [ ] Fumetto → Serie mostra le serie con conteggio reale.
- [ ] I sottogruppi partono chiusi e caricano 50 elementi alla volta.
- [ ] Carica altri aggiunge la pagina successiva senza duplicati.
- [ ] Ricerca globale filtra gruppi, sottogruppi e risultati sull'intero DB.
- [ ] Tipologie senza sottogruppo mantengono il comportamento v2.0.0.
- [ ] Nessun dato esistente viene eliminato durante la migrazione.


## v2.1.1 - anteprima elemento
- [x] Tap su elemento apre modale dettagli di sola lettura.
- [x] Campi vuoti non vengono mostrati.
- [x] Modifica apre la scheda completa esistente.
- [x] Nessuna modifica al database.


## v2.1.2 - foto nella modale anteprima
- [x] Anteprima foto disponibile per qualsiasi tipologia di elemento
- [x] Massimo 3 miniature mostrate nella modale
- [x] Apertura miniatura nel lightbox interno già esistente
- [x] Indicazione foto aggiuntive oltre le prime 3
- [x] Elemento senza foto: pulsante “Nessuna foto · Aggiungi”
- [x] Pulsante senza foto apre direttamente Modifica → Foto
- [x] Pulsante Modifica standard continua ad aprire la scheda completa
- [x] Nessuna modifica allo schema SQLite
- [x] Nessun polling/scheduler/job aggiuntivo
- [x] Versione README coerente con config.yaml (2.1.2)


## v2.1.3 - evidenza sottogruppo aperto
- [x] Il sottogruppo chiuso mantiene lo stile compatto precedente.
- [x] Il sottogruppo aperto è chiaramente evidenziato rispetto agli altri.
- [x] Gli elementi contenuti risultano visivamente separati dall’intestazione del sottogruppo.
- [x] Layout mobile invariato e senza overflow orizzontale.
- [x] Nessuna modifica allo schema SQLite.
- [x] Nessun polling/scheduler/job aggiuntivo.
- [x] Versione README coerente con config.yaml (2.1.3).


## v2.1.4 - Paginazione 50 elementi
- [ ] Primo caricamento: massimo 50 elementi.
- [ ] Successivi sostituisce la pagina precedente.
- [ ] Precedenti torna indietro di 50.
- [ ] Primi torna alla prima pagina.
- [ ] Ultimi apre direttamente l'ultima pagina.
- [ ] Indicatore corretto, es. 701–734 di 734.
- [ ] Funziona nei sottogruppi, es. Fumetti → Zagor.
- [ ] Funziona nei gruppi senza sottogruppi.
- [ ] Ricerca globale funzionante.
- [ ] Apertura elemento funzionante.
- [ ] Modifica elemento funzionante.
- [ ] Database e foto invariati.
