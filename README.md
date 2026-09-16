# Inventario Casa v2.3.5

🇮🇹 **Italiano** | 🇬🇧 [English](README_EN.md)

Inventario Casa è un'App per Home Assistant dedicata alla gestione dell'inventario domestico.

Permette di catalogare oggetti, libri, fumetti e altri beni, organizzandoli per tipologia, ambiente e posizione, con fotografie e campi personalizzati.

## Installazione

Inventario Casa si installa tramite lo Store delle App di Home Assistant.

1. Aprire **Home Assistant**.
2. Andare in **Impostazioni → App → Store delle App**.
3. Aprire il menu **⋮ → Repository**.
4. Aggiungere il repository: `https://github.com/gimalugi/inventario-casa`.
5. Tornare allo Store delle App.
6. Selezionare **Inventario Casa**.
7. Premere **Installa**.
8. Al termine dell'installazione, avviare l'App.

Non è necessario copiare manualmente file nella cartella `/addons`.

## Aggiornamento

Quando viene pubblicata una nuova versione, Home Assistant può segnalarne la disponibilità direttamente dalla pagina dell'App.

L'aggiornamento viene eseguito tramite Home Assistant, senza sostituire manualmente i file dell'App.

Non cancellare i dati dell'App durante l'aggiornamento.

## Persistenza

I dati dell'App sono conservati separatamente dal codice:

- Database: `/data/inventario_casa/inventario.db`
- Foto: `/media/inventario_casa/oggetti`

Gli aggiornamenti mantengono database, fotografie, elementi e campi già presenti.

Novità 0.1.7: ogni campo personalizzato può avere un testo di esempio facoltativo.

Novità 0.1.8: layout responsive smartphone completamente rivisto.

Novità 0.1.9: contrasto mobile migliorato e dettatura vocale nei campi testuali compatibili.

Correzione 0.1.10: migrazione automatica del vecchio schema foto (`caption` -> `label`).

Novità 0.1.11: pannello Tipologie compatto, ricerca, riduzione/espansione ed eliminazione sicura.

Novità 0.1.14: contrasto grafico più marcato su smartphone; sfondo e pannelli più chiari rispetto ai campi di inserimento.

Novità 0.1.15: sfondo interno ispirato al tema Home Assistant ios-dark-mode-blue-red, con card più scure e campi ad alto contrasto.

Novità 0.1.16: card più chiare e trasparenti, effetto vetro, mantenendo i campi di inserimento scuri per contrasto.

Novità 0.1.17: pulsante Aggiungi tipologia spostato accanto al titolo Tipologie, sempre accessibile senza aprire o scorrere l'elenco.

Novità 0.1.18: bordi colorati su pulsanti, tab, statistiche, azioni e tipologie, ispirati alla dashboard Home Assistant dell'utente.

Novità 0.1.19: nella scheda Dettagli vengono mostrati solo i titoli dei campi personalizzati; cliccando un titolo si apre il relativo campo. Un segno ✓ indica i campi già compilati.

Novità 0.1.20: su smartphone, quando si apre la tastiera, il campo attivo viene portato automaticamente al centro della zona visibile.

Novità 0.1.21: Nuovo elemento è chiuso di default e si apre toccando il titolo; la dashboard mostra Cosa possiedo con limite selezionabile 20/50/100, applicato lato database.

Novità 0.1.22: contorni colorati più luminosi e leggermente più spessi.

Novità 0.1.23: corretto il layout mobile dell'editor tipologie; il campo nome occupa tutta la riga e la barra Salva/Annulla/Elimina non copre più i campi sottostanti.

Novità 0.1.24 (Step 1 barcode): aggiunto il campo manuale ISBN / EAN alla tipologia Fumetto. Il Libro mantiene ISBN. Nessuna ricerca automatica o fotocamera ancora: l'inserimento manuale resta sempre disponibile.

Novità 0.1.25 (Step 2 ISBN): pulsante Cerca dati su ISBN/ISBN-EAN per Libro e Fumetto. Ricerca solo su richiesta tramite Open Library, anteprima con conferma e compilazione esclusivamente dei campi vuoti. Inserimento manuale sempre disponibile.

Novità 0.1.26 (Step 3 barcode): scansione ISBN/EAN on-demand dalla fotocamera mobile o da una foto. Il codice rilevato viene inserito nel campo; la ricerca dati resta separata e volontaria. Inserimento manuale sempre disponibile.

Novità 0.1.27: Google Books è la fonte primaria per ISBN, con fallback automatico su Open Library. Inserimento manuale invariato.

Novità 0.1.28:
- Scanner mobile compatibile anche quando BarcodeDetector non è disponibile.
- Fallback locale: i fotogrammi vengono analizzati dall'App tramite pyzbar/zbar solo mentre la schermata scanner è aperta.
- Anche “Usa una foto” utilizza il fallback locale.
- Inserimento manuale sempre disponibile.
- Nessun servizio o scansione in background.

Novità 0.1.29:
- Il pulsante Scansiona codice sceglie automaticamente il metodo disponibile.
- In HTTPS prova la scansione live.
- In accesso locale HTTP apre direttamente la fotocamera di sistema per scattare una foto del barcode.
- La foto viene analizzata dall'add-on e il codice rilevato viene riportato nel campo ISBN/EAN.
- Inserimento manuale sempre disponibile; nessun processo in background.

Novità 0.1.30:
- Elenco elementi molto più compatto: una riga cliccabile con icona, titolo e freccia.
- Rimossi dalla lista principale posizione, descrizione e pulsanti Foto/Modifica/Elimina.
- Toccando un elemento si apre la sua scheda completa.
- Nella scheda restano le sezioni Generale, Dettagli, Posizione, Foto e Note.
- Il comando Elimina è stato spostato nella scheda elemento.

Novità 0.1.31:
- Raggruppamento elenco per Tipologia, Ambiente oppure Nessuno.
- Raggruppamento predefinito: Tipologia.
- Gruppi richiudibili con conteggio elementi.
- Stato aperto/chiuso dei gruppi memorizzato nel browser.
- La ricerca mostra solo i gruppi che contengono risultati.

Novità 0.1.32:
- Intestazione "Cosa possiedo" ottimizzata per smartphone.
- Titolo su una riga separata.
- Controlli Raggruppa e Mostra compatti e affiancati sotto il titolo.
- Migliorata la leggibilità dei gruppi con nomi lunghi.

Novità 0.1.33:
- Bordi più evidenti su tutte le sezioni principali.
- Campi input, select e textarea più riconoscibili.
- Gruppi dell'inventario racchiusi in riquadri più marcati.
- Tipologie con bordi più forti e colori distintivi.
- Elementi dell'elenco meglio separati tra loro.
- Focus dei campi più evidente su mobile.


Inventario Casa 2.1.0 - gestione grandi archivi:
- gruppi richiudibili per Tipologia o Ambiente;
- conteggio reale di tutti gli elementi del gruppo direttamente da SQLite;
- caricamento progressivo: massimo 50 elementi per richiesta;
- pulsante Carica altri per recuperare i successivi 50;
- ricerca globale su tutto il database, compresi i campi personalizzati;
- i gruppi nuovi partono chiusi per evitare caricamenti inutili;
- la scheda di un elemento può essere recuperata singolarmente dal database;
- nessuna modifica distruttiva al database, alle foto o alle tipologie esistenti.

## Inventario Casa 2.3.4 - integrazione temi Home Assistant

- Colori dei testi adattati dinamicamente al tema Home Assistant.
- Supporto migliorato per temi chiari e scuri.
- Campi di inserimento, menu, textarea e placeholder adattati al tema attivo.
- Migliore contrasto e separazione visiva di card e pannelli.
- Migliorata la leggibilità della schermata principale con temi chiari.
- Migliorata la visualizzazione del riquadro informativo della sezione Foto.
- Mantenuti i colori semantici per successo, errore, pericolo e accenti.
- Corretto il caricamento del layer grafico tramite WSGI.
- Nessuna modifica al database o al relativo schema.

## Inventario Casa 2.3.5 - gestione sicura della fotocamera

- La scansione ISBN/EAN tramite fotocamera è disponibile solo in connessioni sicure HTTPS.
- In connessioni HTTP il pulsante di scansione rimane visibile ma viene disabilitato.
- Inserimento manuale di ISBN/EAN e ricerca dati rimangono sempre disponibili.
- In HTTPS viene utilizzata la scansione live quando supportata dal browser.
- Se la scansione live non è disponibile, rimane disponibile il fallback tramite foto.
- Aggiunta una protezione anche al fallback fotografico per impedire l'accesso alla fotocamera in contesti non sicuri.
- Aggiornati i messaggi della finestra di scansione per distinguere correttamente il comportamento HTTP/HTTPS.
- Migliorata la leggibilità delle opzioni dei menu a tendina nativi su Windows/Chrome.
- Nessuna modifica al database o al relativo schema.

