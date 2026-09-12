## 2.3.2

- Migliorato il pulsante Scarica nella finestra Backup.
- Data e ora dei backup mostrate in formato italiano.
- Nessuna modifica alla logica di backup, restore, Recovery Mode o schema database.

## 2.3.1

- Migliorata la grafica della finestra Backup database.
- Aggiunti badge per data, dimensione, schema e stato integrità.
- Migliorata la disposizione dei pulsanti Scarica e Ripristina.
- Ottimizzazione mobile della finestra Backup.
- Nessuna modifica alla logica di backup, restore, Recovery Mode o schema database.

## 2.3.0
- Nuova sezione Backup database nell'interfaccia.
- Creazione manuale di backup SQLite consistenti.
- Elenco backup con data, dimensione, schema e stato di integrità.
- Download dei backup dall'interfaccia.
- Ripristino guidato con doppia conferma.
- Backup automatico del database corrente prima di un restore.
- Verifica `PRAGMA integrity_check` prima e dopo il ripristino.
- Modalità Recovery se l'inizializzazione o una migrazione DB falliscono.
- In Recovery i backup restano consultabili, scaricabili e ripristinabili.
- Nessun processo, scheduler o controllo periodico in background.
- `CURRENT_SCHEMA_VERSION` resta 1: questa release non modifica lo schema dati.

## 2.2.3
- Introdotta la versione interna dello schema SQLite (`schema_version`).
- Aggiunta la tabella tecnica `app_meta`.
- Backup automatico del database prima delle migrazioni dello schema.
- Backup salvati in `/media/inventario_casa/db_backups/`.
- Verifica automatica del backup con `PRAGMA integrity_check`.
- La migrazione viene interrotta se il backup non è valido.
- Nessun backup aggiuntivo durante i normali riavvii quando lo schema è aggiornato.
- Nessun processo in background.
- Nessuna modifica ai dati inventariati o alle foto.

## 2.2.2
- Corretto su smartphone il campo Nome dei campi personalizzati nell'editor Tipologie.
- Il pulsante microfono non occupa più tutta la larghezza e non nasconde il nome del campo.
- Aggiunto pulsante × di chiusura in alto a destra alle principali finestre dell'app.
- Pulsante × disponibile in Modifica tipologia, Dettagli elemento, Scheda elemento e Scanner ISBN/EAN.
- Nessuna modifica al database, agli elementi o alle foto.
- Nessun processo in background.

## 2.2.1

- Tema grafico collegato dinamicamente ai colori del tema Home Assistant quando eseguito tramite Ingress.
- Mantiene il precedente sfondo Inventario Casa come fallback.
- Nessun polling o attività periodica per il tema.
- Aggiunto pulsante × nella barra di ricerca.
- Il pulsante × appare solo quando è presente del testo e ripristina immediatamente l'inventario completo.
- Nessuna modifica al database o ai dati dell'inventario.

# CHANGELOG

## 2.1.5
- Ordinamento numerico naturale degli elementi che possiedono il campo `Numero`.
- Corretto l'ordine 1, 10, 11, 2 in 1, 2, 3 ... 10, 11.
- Gestito il campo `Suffisso numero`: il BIS viene mostrato dopo il numero principale.
- Correzione applicata sia ai gruppi sia ai sottogruppi.
- Paginazione da 50 elementi della v2.1.4 invariata.
- Tipologie senza campo Numero continuano ad essere ordinate alfabeticamente.
- Nessuna modifica ai dati SQLite o alle foto.
- Nessun processo in background.

## 2.1.4
- Paginazione reale da 50 elementi per gruppi e sottogruppi.
- La pagina successiva sostituisce quella precedente invece di accumularla.
- Aggiunti i comandi Primi, Precedenti, Successivi e Ultimi.
- Mostrato l'intervallo corrente, ad esempio 701–734 di 734.
- Ottimizzato il comportamento per raccolte molto grandi come Zagor.
- In memoria vengono mantenuti soltanto gli elementi delle pagine attualmente visualizzate.
- Nessuna modifica al database o alle API.
- Nessun processo in background.

## 2.1.3
- Evidenziato chiaramente il sottogruppo attualmente aperto nell’elenco.
- Intestazione del sottogruppo aperto con accento ciano/blu, bordo luminoso e conteggio più visibile.
- Corpo degli elementi del sottogruppo separato con una guida verticale colorata e sfondo leggermente distinto.
- Migliorata la leggibilità soprattutto quando una serie contiene molti elementi.
- Nessuna modifica al database o alle API.

## 2.1.2
- Anteprima elemento estesa a tutte le tipologie con visualizzazione delle foto disponibili.
- Mostrate fino a 3 miniature nella modale; tocco sulla miniatura apre il lightbox interno esistente.
- Se ci sono più di 3 foto viene indicato quante altre sono disponibili nella scheda Modifica.
- Se l’elemento non ha foto compare “📷 Nessuna foto · Aggiungi”, che apre direttamente Modifica → Foto.
- Nessuna modifica al database o al formato delle foto.
- Nessun polling, scheduler o processo in background aggiuntivo.

## 2.1.1
- Toccando un elemento si apre una modale compatta di sola lettura con i dettagli disponibili.
- La modale mostra campi personalizzati, posizione, descrizione, tag e note solo quando valorizzati.
- Aggiunto pulsante Modifica per aprire la scheda completa.
- Nessuna modifica al database.

## 2.1.0
- Sottoraggruppamenti configurabili per ogni tipologia tramite uno dei suoi campi personalizzati.
- Esempio: Fumetto → Serie → elementi.
- Conteggio reale per sottogruppo calcolato da SQLite.
- Sottogruppi richiudibili e caricamento progressivo di 50 elementi.
- Ricerca globale applicata anche ai conteggi e ai risultati dei sottogruppi.
- Nessun caricamento massivo e nessun processo in background.
- Migrazione compatibile: aggiunta la sola preferenza subgroup_field_id alle tipologie.


## 2.0.0
- Nuova architettura della lista pensata per migliaia di elementi.
- Conteggi dei gruppi calcolati direttamente da SQLite (es. Fumetti 2000).
- Ogni gruppo carica al massimo 50 elementi per volta.
- Aggiunto Carica altri per i successivi 50 elementi.
- Ricerca globale eseguita sull'intero database, inclusi i campi personalizzati.
- Gruppi nuovi chiusi per impostazione predefinita: nessun caricamento massivo all'apertura.
- Accesso puntuale alla scheda elemento tramite API dedicata.
- Rimossa la vecchia selezione globale 20/50/100, sostituita dal caricamento progressivo.
- Compatibilità con database, foto, tipologie e campi esistenti.
- Nessuna migrazione distruttiva.


## 0.1.33
- Aumentato il contrasto dei bordi di pannelli, campi e sezioni.
- Tipologie con bordi colorati più evidenti.
- Gruppi inventario più distinguibili con riquadro dedicato.
- Elementi singoli più separati visivamente.
- Migliorato il focus di input/select/textarea.
- Nessuna modifica al database.


## 0.1.32
- Corretto layout mobile della sezione Cosa possiedo.
- Titolo separato dai controlli.
- Raggruppa e Mostra affiancati in modo responsive.
- Migliorato il comportamento dei nomi lunghi nei gruppi.
- Nessuna modifica al database.


## 0.1.31
- Aggiunto selettore Raggruppa: Tipologia / Ambiente / Nessuno.
- Tipologia è il raggruppamento predefinito.
- Gruppi richiudibili con conteggio.
- Memorizzazione locale dello stato aperto/chiuso.
- Ricerca compatibile con il raggruppamento.
- Nessuna modifica al database.


## 0.1.30
- Lista elementi compatta a solo titolo, cliccabile.
- Apertura della scheda elemento toccando la riga.
- Foto, modifica e cancellazione gestite dalla scheda elemento.
- Pulsante Elimina aggiunto alla scheda.
- Nessuna modifica al database.


## 0.1.29
- Scanner ISBN/EAN adattivo tra HTTPS e accesso locale HTTP.
- In HTTP, `Scansiona codice` apre direttamente la fotocamera di sistema tramite `capture=environment`.
- In HTTPS resta disponibile la scansione live.
- Se la scansione live viene bloccata, viene proposto chiaramente il fallback `Scatta foto del codice`.
- Inserimento manuale sempre disponibile.
- Nessuna modifica al database e nessun processo in background.


## 0.1.28
- Aggiunto fallback barcode lato App con pyzbar/zbar quando il browser non espone BarcodeDetector.
- La scansione live continua a usare la fotocamera e analizza un fotogramma ogni ~500 ms solo durante l'apertura dello scanner.
- “Usa una foto” funziona anche senza BarcodeDetector.
- Inserimento manuale sempre disponibile.
- Nessuna modifica al database.


## 0.1.27
- Google Books come fonte primaria per la ricerca ISBN.
- Fallback automatico su Open Library.
- Preferenza per risultati con ISBN esattamente corrispondente.
- Fonte mostrata nella conferma.
- Inserimento manuale sempre disponibile.
- Nessuna modifica al database.


## 0.1.26
- Step 3 barcode: aggiunto `📷 Scansiona codice` sui campi ISBN / ISBN-EAN.
- Scansione on-demand tramite fotocamera posteriore del dispositivo.
- Aggiunto fallback `📸 Usa una foto` per leggere un barcode da un'immagine acquisita.
- Il codice rilevato viene inserito nel campo ma la ricerca metadati non parte automaticamente.
- Inserimento manuale e `🔎 Cerca dati` restano sempre disponibili.
- La fotocamera viene arrestata appena il codice è letto o il dialog viene chiuso.
- Nessun processo in background e nessuna modifica al database.


## 0.1.25
- Step 2 ISBN: aggiunto `🔎 Cerca dati` ai campi ISBN / ISBN-EAN.
- Ricerca on-demand su Open Library; nessun processo in background.
- Mostra un'anteprima dei dati e chiede conferma prima di applicarli.
- Compila soltanto i campi vuoti; i dati già inseriti manualmente non vengono sovrascritti.
- Recupero previsto: titolo, autore, editore, data/anno quando disponibili.
- EAN non ISBN viene segnalato come non supportato in questo step.
- Nessuna modifica distruttiva al database.


## 0.1.24
- Step 1 per ISBN/EAN: aggiunto `ISBN / EAN` alla tipologia Fumetto.
- La tipologia Libro continua a usare il campo ISBN esistente.
- Inserimento manuale sempre disponibile.
- Nessuna fotocamera, ricerca esterna o processo in background in questo step.
- Migrazione additiva: nessuna modifica distruttiva ai dati esistenti.


## 0.1.23
- Corretto il layout mobile dell'editor `Modifica tipologia`.
- Il campo nome personalizzato con microfono occupa ora tutta la larghezza.
- Migliorata la disposizione di tipo campo, obbligatorio e pulsanti spostamento.
- La barra `Elimina / Annulla / Salva tipologia` non è più sticky e non copre i campi sottostanti.
- Migliorata la separazione visiva tra i singoli campi personalizzati.
- Nessuna modifica a database o API.


## 0.1.22
- Contorni colorati più evidenti e leggermente più spessi.
- Glow leggero su tab, statistiche, tipologie e pulsanti azione.
- Nessuna modifica a database o logica.


## 0.1.21
- `Nuovo elemento` ora è chiuso di default e si apre toccando il titolo.
- Dopo il salvataggio il pannello di inserimento torna automaticamente chiuso.
- La sezione elenco è rinominata `Cosa possiedo`.
- Aggiunto selettore 20 / 50 / 100 elementi visibili.
- Il limite viene ricordato nel browser.
- Il limite è applicato direttamente alla query SQLite, evitando di caricare inutilmente tutti gli oggetti.
- Mostrato `Visualizzati X di Y elementi` quando l'inventario supera il limite.
- Anche i risultati di ricerca rispettano il limite selezionato.
- Nessun polling o processo in background.


## 0.1.20
- Migliorata l'ergonomia su smartphone quando compare la tastiera.
- Il campo attivo viene portato automaticamente nella zona visibile.
- Gestito anche il ridimensionamento della viewport causato dalla tastiera virtuale.
- Aggiunto spazio inferiore di sicurezza per evitare che gli ultimi campi restino coperti.
- Nessuna modifica a database o API.


## 0.1.19
- Scheda Dettagli resa compatta con campi personalizzati a fisarmonica.
- Vengono mostrati inizialmente solo i titoli dei campi.
- Cliccando un titolo si apre esclusivamente il relativo campo di inserimento.
- Aprendo un campo, gli altri vengono richiusi automaticamente.
- I campi già compilati mostrano un segno `✓`.
- Funziona sia in creazione sia in modifica elemento.
- Nessuna modifica a database o API.


## 0.1.18
- Aggiunti bordi colorati ai pulsanti principali, ispirati alla dashboard Home Assistant.
- Tab Generale/Dettagli/Posizione/Foto/Note differenziati con colori diversi.
- Card statistiche con accenti blu, verde e rosa.
- Pulsanti azione elementi con colori distinti: foto/ciano, modifica/giallo, elimina/rosso.
- Tipologie con bordi colorati a rotazione per rendere la GUI più viva.
- Effetti volutamente leggeri per non appesantire la leggibilità.
- Nessuna modifica a database o logica dell'app.


## 0.1.17
- Spostato il comando per creare una nuova tipologia accanto al titolo `Tipologie`.
- Il pulsante è sempre accessibile senza aprire o scorrere l'elenco.
- Su smartphone il pulsante diventa compatto e mostra solo il simbolo `+`.
- Il vecchio pulsante in fondo all'elenco viene nascosto.
- Nessuna modifica a database, API o logica dei dati.


## 0.1.16
- Card e pannelli resi più chiari e trasparenti.
- Effetto vetro con blur leggero per lasciar intravedere lo sfondo ios-dark-mode-blue-red.
- Sezioni annidate leggermente più luminose per migliorare la separazione visiva.
- Campi di inserimento mantenuti scuri per un contrasto netto.
- Nessuna modifica a database, API o logica dell'app.
- Nessun nuovo processo in background.


## 0.1.15
- Sfondo interno ridisegnato per armonizzarsi con il tema Home Assistant `ios-dark-mode-blue-red`.
- Gradiente blu/viola/rosso visibile anche su smartphone.
- Card e pannelli resi più scuri e semi-opachi per staccarsi nettamente dallo sfondo.
- Campi di inserimento ancora più scuri, con bordi più chiari e focus azzurro.
- Migliorata la profondità visiva delle sezioni annidate.
- Nessuna modifica a database, API o logica dell'app.
- Nessun nuovo processo in background.


## 0.1.14
- Corretto il numero versione mostrato nella documentazione dell'App.
- Sfondo generale molto più chiaro e visibile su smartphone.
- Pannelli/sezioni schiariti per distinguersi nettamente dai campi di inserimento.
- Campi input/select/textarea mantenuti scuri con bordo più evidente.
- Nessuna modifica al database o alle funzioni.
- Nessun nuovo processo in background.


## 0.1.13
- Sfondo generale schiarito in grigio antracite.
- Pannelli/sezioni più chiari rispetto ai campi di inserimento.
- Campi input/select/textarea mantenuti scuri per creare maggiore contrasto.
- Bordi dei campi più visibili e focus azzurro.
- Placeholder più leggibili su smartphone.
- Nessuna modifica a database, API o funzioni dell'inventario.
- Nessun nuovo processo in background.


## 0.1.12
- Corretto errore 401 Unauthorized aprendo una foto da smartphone tramite Home Assistant Ingress.
- Le foto ora si aprono in un visualizzatore interno (lightbox), senza creare una nuova scheda del browser.
- Il visualizzatore mantiene il percorso/autorizzazione Ingress e funziona anche su mobile.
- Chiusura con pulsante ×, tocco sullo sfondo o tasto Esc.
- Nessun processo o controllo aggiuntivo in background.


## 0.1.11
- Pannello Tipologie reso compatto e scalabile.
- Aggiunta ricerca rapida delle tipologie.
- Ogni tipologia è ora una riga compatta con icona, nome e numero di campi attivi; clic sulla riga apre l'editor.
- Pannello Tipologie riducibile/espandibile con stato ricordato nel browser.
- Aggiunta eliminazione sicura delle tipologie: la cancellazione è bloccata se la tipologia è usata da uno o più elementi.
- Migliorata la disposizione del pannello Tipologie su smartphone.


## 0.1.10
- Corretto errore `sqlite3.OperationalError: no such column: label`.
- Aggiunta migrazione automatica della tabella foto per database creati con versioni precedenti.
- Se il vecchio database usa `caption`, il contenuto viene copiato automaticamente nel nuovo campo `label`.
- Nessuna cancellazione di elementi, tipologie, campi o foto esistenti.
- Conservate le migliorie mobile e la dettatura vocale della v0.1.9.


## 0.1.9
- Migliorato il contrasto su smartphone: campi più chiari del fondo, bordi più visibili e placeholder più leggibili.
- Focus dei campi più evidente.
- Aggiunta dettatura vocale con pulsante 🎤 nei campi Nome, Descrizione, Note, Tag e nei campi personalizzati Testo/Testo lungo.
- Pulsante microfono disabilitato automaticamente se il browser non supporta il riconoscimento vocale.
- Conservate tutte le funzioni della v0.1.8.


## 0.1.8
- Interfaccia smartphone rivista senza rimuovere funzioni.
- Header e ricerca ottimizzati per schermi stretti.
- Form e campi personalizzati a una colonna su mobile.
- Schede scorrevoli orizzontalmente con controlli touch più grandi.
- Scheda elemento e modifica tipologia a tutto schermo su smartphone.
- Pulsanti Salva/Chiudi più facili da raggiungere.
- Lista elementi e pulsanti azione non si comprimono lateralmente.
- Editor dei campi tipologia riorganizzato in card verticali.
- Griglia foto ottimizzata a 2 colonne su smartphone.
- Input a 16 px per evitare lo zoom automatico sui browser mobili.
- Aggiunti accorgimenti contro overflow orizzontale.


## 0.1.7
- Aggiunto il campo facoltativo “Testo di esempio” ai campi personalizzati.
- Il testo appare come placeholder leggero nei campi testo, numero, data e testo lungo.
- Nei campi Elenco viene mostrato come suggerimento leggero sotto il menu.
- Migrazione automatica del database senza perdita dati.
- Aggiornata la checklist di regressione.


## 0.1.6
- Ripristinato il blocco completo "Nuovo elemento".
- Ripristinate le schede Generale, Dettagli, Posizione, Foto e Note.
- Mantenuta e completata la modifica delle tipologie.
- Aggiunto riordino dei campi con frecce su/giù.
- I campi nascosti vengono disattivati, non cancellati.
- Migrazione Fumetto corretta: Condizione e Difetti vengono aggiunti se mancanti.
- Foto multiple ottimizzate e salvate in /media/inventario_casa/oggetti.
- Profilo automatico: Fumetto usa qualità collezionabili.
- Aggiunta checklist di regressione al pacchetto.

## 0.1.5
- Prima introduzione della modifica tipologie, ma release incompleta lato inserimento elementi.
