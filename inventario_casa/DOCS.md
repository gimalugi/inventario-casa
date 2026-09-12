# 🏠 Inventario Casa

**Inventario Casa** è un'app per Home Assistant pensata per catalogare ciò che possiedi e sapere rapidamente **che cosa hai e dove si trova**.

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
- Codice del contenitore, se utilizzato

In questo modo è possibile sapere non solo se possiedi un oggetto, ma anche **dove recuperarlo fisicamente**.

### 🏷️ Tipologie personalizzabili
L'inventario utilizza un unico archivio globale, ma gli elementi possono appartenere a tipologie differenti.

Sono disponibili tipologie predefinite come:

- Oggetto
- Libro
- Fumetto
- Rivista

È inoltre possibile creare liberamente nuove tipologie, ad esempio elettronica, videogiochi, VHS o qualsiasi altra collezione.

### 🧩 Campi personalizzati
Ogni tipologia può avere campi propri, configurabili dall'utente.

Sono supportati campi:

- Testo
- Numero
- Data
- Testo esteso
- Selezione da elenco
- Casella di controllo

I campi possono essere obbligatori o facoltativi, ordinati e attivati/disattivati secondo necessità.

### 🔎 Ricerca globale
La ricerca permette di trovare rapidamente gli elementi dell'inventario utilizzando sia i dati principali sia i campi personalizzati.

Il pulsante **×** nel campo di ricerca cancella il testo e ripristina immediatamente l'inventario completo.

### 🗂️ Raggruppamenti e sottogruppi
Gli elementi possono essere visualizzati raggruppati per tipologia e, quando configurato, ulteriormente suddivisi in sottogruppi.

Ad esempio, i fumetti possono essere raggruppati per **Serie**.

L'elenco utilizza paginazione per mantenere l'interfaccia veloce anche con inventari numerosi.

### 🔢 Ordinamento numerico naturale
Le raccolte che utilizzano un campo **Numero** vengono ordinate numericamente in modo naturale, evitando ordinamenti alfabetici come `1, 10, 11, 2`.

È supportato anche un eventuale **Suffisso numero**.

### 📷 Fotografie
Ogni elemento può avere più fotografie.

Le immagini vengono elaborate e ottimizzate automaticamente e possono essere aperte nell'interfaccia tramite visualizzazione ingrandita.

### 📚 ISBN e codici a barre
Per libri e altri elementi compatibili è possibile utilizzare ISBN o codici a barre per facilitare l'inserimento dei dati.

La lettura può utilizzare la fotocamera quando il browser e la connessione lo consentono; l'inserimento manuale rimane sempre disponibile.

### 🎙️ Dettatura vocale
Nei browser compatibili è disponibile la dettatura vocale per velocizzare la compilazione dei campi testuali.

## 🎨 Integrazione con Home Assistant

Quando Inventario Casa viene aperto tramite **Ingress**, l'interfaccia utilizza dinamicamente i colori e lo sfondo del tema Home Assistant attualmente selezionato.

Se le informazioni del tema non sono disponibili, viene utilizzata automaticamente la grafica predefinita di Inventario Casa.

L'app non esegue polling o attività periodiche per il tema: la sincronizzazione avviene solo quando necessario.

## 💾 Dove vengono salvati i dati

Il database dell'inventario è memorizzato in:

`/data/inventario_casa/inventario.db`

Le fotografie sono memorizzate separatamente in:

`/media/inventario_casa/oggetti/`

La separazione consente di mantenere le fotografie fuori dai dati interni dell'app e di gestirne il backup separatamente.

## 🔄 Aggiornamenti

Gli aggiornamenti dell'app sono progettati per **conservare il database e gli elementi già catalogati**.

Non è necessario cancellare i dati dell'app durante un normale aggiornamento.

Prima di operazioni straordinarie o migrazioni è comunque consigliato conservare una copia di sicurezza del database.

## ⚙️ Funzionamento

Inventario Casa è un'app passiva: non utilizza scheduler, cron, scansioni continue o processi periodici in background.

Il servizio rimane disponibile per rispondere alle richieste dell'interfaccia e le operazioni vengono eseguite quando richieste dall'utente.

---

## Versione 2.2.1

Questa versione introduce:

- collegamento dinamico al tema grafico di Home Assistant tramite Ingress;
- mantenimento della grafica Inventario Casa come fallback;
- pulsante **×** per cancellare rapidamente la ricerca;
- font maggiormente coerente con l'interfaccia Home Assistant;
- nessuna modifica al database o ai dati dell'inventario.
