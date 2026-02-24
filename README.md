# Adventure

Repository per progettare un'avventura testuale **dark-gothic** guidata da prompt, con worldbuilding e regole di gioco definiti in file di testo.

## Di cosa si tratta

Sì: questo progetto sembra essere un **pacchetto di prompt + database del mondo** per far interpretare a un LLM il ruolo di game engine narrativo.

In pratica:
- `database_mondo.txt` contiene mappa, stanze, oggetti, eventi a tempo, condizioni di vittoria/sconfitta e testi canonici da non alterare.
- `promp_adv_v1.txt`, `promp_adv_v2.txt`, `promp_adv_v3.txt` sono iterazioni del prompt di sistema/ruolo, sempre più strutturate.
- La versione `v3` introduce anche la generazione immagine obbligatoria (`image_generation`) e un ordine di output molto rigido.

## Struttura del repository

- `database_mondo.txt` — Base dati narrativa e logica del mondo (stanze, uscite, regole, eventi, item, trigger).
- `promp_adv_v1.txt` — Prima versione del prompt motore.
- `promp_adv_v2.txt` — Revisione con regole anti-spoiler per elementi nascosti.
- `promp_adv_v3.txt` — Versione più completa, con tool-call immagine e formato output obbligatorio.
- `LICENSE` — Licenza del progetto.

## Come usarlo

1. Scegli la versione del prompt (`v1`, `v2` o `v3`) in base al livello di rigidità desiderato.
2. Usa quel prompt come **System Prompt** nel tuo client LLM.
3. Rendi disponibile a modello il contenuto di `database_mondo.txt` (come contesto o file allegato).
4. Avvia la sessione: il gioco parte dal **Cancello Arrugginito** con stato iniziale già definito dal prompt.
5. Inserisci i comandi del giocatore (es. “apri la cassetta”, “vai nord”, “usa osso carnoso”).

## Note progettuali

- Il repository è orientato al **design narrativo e delle regole**, non contiene codice applicativo.
- Il cuore del sistema è la coerenza tra:
  - stato dinamico (salute, inventario, turni, flag),
  - memoria statica (`database_mondo.txt`),
  - formato di risposta imposto dal prompt.

## Possibili sviluppi

- Correzione refusi/normalizzazione del database.
- Conversione del database in formato strutturato (JSON/YAML).
- Script di validazione automatica della mappa (coerenza uscite, stanze raggiungibili, item unici).
- Interfaccia CLI/Web per giocare senza copiare manualmente i prompt.
