#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║         UNIVERSAL TEXT ADVENTURE ENGINE (Data-Driven)        ║
║   Engine Python + Ollama (Locale) + Regole JSON Universali   ║
╚══════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import json
import os
import re
import sys
import textwrap
from typing import Dict, List, Optional, Set, Tuple, Any

# ═══════════════════════════════════════════════════════
#  CONFIGURAZIONE OLLAMA (LOCALE)
# ═══════════════════════════════════════════════════════

MODEL      = "gemma3:27b-cloud"   
OLLAMA_URL = "http://localhost:11434/api/chat"

DB_FILE  = os.path.join(os.path.dirname(__file__), "database_mondo_data_driven.json")
USE_LLM  = ("--no-llm" not in sys.argv)
COL      = 82   
_DIREZIONI_RAPIDE = {
    "n": "NORD", "s": "SUD", "e": "EST", "o": "OVEST",
    "nord": "NORD", "sud": "SUD", "est": "EST", "ovest": "OVEST",
    "su": "SU", "giù": "GIU", "giu": "GIU", "up": "SU", "down": "GIU"
}
# ═══════════════════════════════════════════════════════
#  UTILITY OUTPUT E TRADUZIONE
# ═══════════════════════════════════════════════════════

def wrap(t: str) -> str:
    return "\n".join(textwrap.fill(p, width=COL) for p in str(t).splitlines())

def stampa(t: str, prefisso: str = ""):
    for riga in wrap(t).splitlines():
        print(prefisso + riga)

def sep(c: str = "─"):
    print(c * COL)

def hdr(t: str):
    sep("═")
    print(f"  ✦  {t}")
    sep("═")

def llm_traduci(testo: str, lingua: str) -> str:
    if not USE_LLM or not testo:
        return testo
    if lingua.lower() in ("italiano", "it", "ita"):
        return testo

    system_prompt = (
        f"Sei il traduttore silente di un'avventura testuale. "
        f"Traduci la seguente frase in {lingua.upper()}. "
        f"REGOLE: "
        f"1. Mantieni ESATTAMENTE la formattazione originale e le emoji (es. ✓, ⚠, 🔲, 🔑, 🎒, 🔆). "
        f"2. NON INIZIARE MAI con 'Okay', 'Here is', 'Sure' o spiegazioni. Solo la pura traduzione."
    )
    try:
        import requests
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages":[{"role": "system", "content": system_prompt}, {"role": "user", "content": testo}],
                "stream": False, "options": {"temperature": 0.1}
            },
            timeout=15, 
        )
        r.raise_for_status()
        raw = r.json()["message"]["content"].strip()
        raw = re.sub(r'^(Here is|Sure|Ok|Okay|Translation:).*?\n', '', raw, flags=re.IGNORECASE).strip()
        return raw
    except:
        return testo

# ═══════════════════════════════════════════════════════
#  CHIAMATE LLM  (OLLAMA)
# ═══════════════════════════════════════════════════════

def _llm_call(system: str, user: str, max_tokens: int = 400, temp: float = 0.7, json_format: bool = False) -> Optional[str]:
    if not USE_LLM: return None
    payload = {
        "model": MODEL,
        "messages":[{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": temp, "num_predict": max_tokens}
    }
    if json_format: payload["format"] = "json"
    
    try:
        import requests
        r = requests.post(OLLAMA_URL, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        print(f"\n[DEBUG LLM ERROR] {e}")
        return None

_SYSTEM_NARRATORE = (
    "Sei il Game Master di un'avventura testuale. "
    "Riscrivi la descrizione della stanza fornita per renderla immersiva (massimo 130 parole). "
    "REGOLE FONDAMENTALI: "
    "1. Menziona esplicitamente TUTTI gli oggetti e TUTTE le uscite fornite. "
    "2. Non inventare nulla di non fornito. "
    "3. Scrivi in seconda persona singolare. "
    "4. TRADUZIONE: Scrivi ESCLUSIVAMENTE nella lingua richiesta. "
    "5. NON INIZIARE MAI con saluti come 'Okay', 'Here is'. Inizia direttamente con la narrazione."
)

_SYSTEM_PARSER = """Sei il traduttore semantico di un'avventura testuale.
Traduci l'input del giocatore (in qualsiasi lingua) in una LISTA JSON in ITALIANO.

REGOLE:
1. Formato SOLO JSON. Nessun testo extra.
2. Risolvi i pronomi basandoti sugli oggetti nel contesto.
3. Usa solo l'elenco esatto dei nomi oggetti presenti nel contesto.
4. Azioni permesse: vai, prendi, lascia, esamina, usa, apri, leggi, attacca, dai, cerca, sposta, fuggi, inventario, salute, aiuto, inserisci, mescola, ripara, riordina, riempi.
5. Se dice "prendi tutto", genera un array di oggetti "prendi" per ogni oggetto visibile.

Formato esempio:[{"a": "usa", "o": "chiave di ferro", "su": "botola"}]
"""

def llm_descrivi(ctx: str) -> Optional[str]:
    return _llm_call(_SYSTEM_NARRATORE, ctx, temp=0.7)

def llm_parse(stato: 'Stato', inp: str) -> Optional[List[Dict]]:
    nomi_visibili = [stato.oggetti[id_obj]["nome"] for id_obj in stato.oggetti_visibili_stanza()]
    nomi_inv = [stato.oggetti[id_obj]["nome"] for id_obj in stato.inv]
    
    ctx = f"- Oggetti stanza: {', '.join(nomi_visibili) or 'nessuno'}\n- Inventario: {', '.join(nomi_inv) or 'vuoto'}"
    user_prompt = f"Contesto:\n{ctx}\n\nInput giocatore: '{inp}'"
    
    raw = _llm_call(_SYSTEM_PARSER, user_prompt, temp=0.0, json_format=True)
    if raw:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        try:
            parsed = json.loads(raw)
        except:
            m = re.search(r'(\[.*?\]|\{.*?\})', raw, re.DOTALL)
            if m: parsed = json.loads(m.group(1))
            else: return None
            
        if isinstance(parsed, dict) and "a" in parsed: return [parsed]
        elif isinstance(parsed, list) and len(parsed)>0 and "a" in parsed[0]: return parsed
    return None


# ═══════════════════════════════════════════════════════
#  STATO DI GIOCO UNIVERSALE
# ═══════════════════════════════════════════════════════

class Stato:
    def __init__(self, db: Dict):
        self.db = db
        self.stanze = {s["id"]: s for s in db["stanze"]}
        self.oggetti = {o["id"]: o for o in db["oggetti"]}
        
        cfg = db.get("configurazione", {})
        self.stanza = cfg.get("stanza_iniziale", list(self.stanze.keys())[0])
        self.salute_max = cfg.get("salute_max", 100)
        self.salute = self.salute_max
        self.variabili = dict(cfg.get("variabili_iniziali", {}))
        
        self.inv: List[str] = []
        self.flags: Dict[str, bool] = {}
        self.rivelati: Dict[str, List[str]] = {}       # stanza_id -> [obj_id]
        self.uscite_sbloccate: Dict[str, List[str]] = {} # stanza_id -> [direzioni]
        
        self.turno = 1
        self.t_stanza: Dict[str, int] = {self.stanza: 1}
        self.prima_visita: Set[str] = set()
        self.lingua = "italiano"

    @property
    def ds(self) -> Dict:
        return self.stanze[self.stanza]

    def ts(self, s: Optional[str] = None) -> int:
        return self.t_stanza.get(s or self.stanza, 0)

    def morto(self) -> bool:
        return self.salute <= 0
        
    def trova_id_oggetto(self, kw: str, liste_cerca: List[str]) -> Optional[str]:
        """Trova l'ID di un oggetto cercando per keyword nei nomi degli oggetti forniti."""
        if not kw: return None
        parole_chiave = kw.lower().split()
        for obj_id in liste_cerca:
            nome_obj = self.oggetti[obj_id]["nome"].lower()
            if all(p in nome_obj for p in parole_chiave):
                return obj_id
        return None

    def oggetti_visibili_stanza(self, stanza_id: str = None) -> List[str]:
        sid = stanza_id or self.stanza
        base = list(self.stanze[sid].get("oggetti_visibili",[]))
        rivelati = self.rivelati.get(sid, [])
        return [o for o in (base + rivelati) if o not in self.inv]

    def uscite_disponibili(self) -> List[Dict]:
        uscite =[]
        sbloccate = self.uscite_sbloccate.get(self.stanza,[])
        for u in self.ds.get("uscite",[]):
            # Se è bloccata, mostrala solo se il flag l'ha sbloccata
            if u.get("bloccata", False):
                flag_sblocco = u.get("sbloccata_da_flag")
                if (flag_sblocco and self.flags.get(flag_sblocco)) or u["direzione"] in sbloccate:
                    uscite.append(u)
            else:
                uscite.append(u)
        return uscite

    def esporta_dati(self) -> Dict:
        return {
            "stanza": self.stanza, "salute": self.salute, "inv": self.inv,
            "flags": self.flags, "variabili": self.variabili, "turno": self.turno,
            "t_stanza": self.t_stanza, "rivelati": self.rivelati,
            "uscite_sbloccate": self.uscite_sbloccate,
            "prima_visita": list(self.prima_visita), "lingua": self.lingua
        }

    def importa_dati(self, d: Dict):
        self.stanza = d.get("stanza", self.stanza)
        self.salute = d.get("salute", self.salute_max)
        self.inv = d.get("inv",[])
        self.flags = d.get("flags", {})
        self.variabili = d.get("variabili", {})
        self.turno = d.get("turno", 1)
        self.t_stanza = d.get("t_stanza", {})
        self.rivelati = d.get("rivelati", {})
        self.uscite_sbloccate = d.get("uscite_sbloccate", {})
        self.prima_visita = set(d.get("prima_visita",[]))
        self.lingua = d.get("lingua", "italiano")

# ═══════════════════════════════════════════════════════
#  MOTORE DI LOGICA (RULE ENGINE)
# ═══════════════════════════════════════════════════════

def valuta_condizioni(stato: Stato, condizioni: List[Dict]) -> bool:
    """Ritorna True se TUTTE le condizioni nell'array sono verificate."""
    for c in condizioni:
        tipo = c["tipo"]
        if tipo == "ha_oggetto":
            if c["oggetto"] not in stato.inv: return False
        elif tipo == "flag_vero":
            if not stato.flags.get(c["nome"], False): return False
        elif tipo == "flag_falso":
            if stato.flags.get(c["nome"], False): return False
        elif tipo == "turni_stanza_uguale":
            if stato.ts() != c["valore"]: return False
        elif tipo == "turni_stanza_maggior_uguale":
            if stato.ts() < c["valore"]: return False
        elif tipo == "variabile_maggiore_di":
            if stato.variabili.get(c["nome"], 0) <= c["valore"]: return False
        elif tipo == "stato_diverso":
            # Per generalizzare, usiamo i flag come stati (es. cassetta_aperta)
            if stato.flags.get(c["valore"], False): return False 
    return True

def esegui_effetti(stato: Stato, effetti: List[Dict]) -> str:
    """Esegue gli effetti e ritorna l'output testuale."""
    msg_out = []
    for e in effetti:
        tipo = e["tipo"]
        if tipo == "messaggio":
            msg_out.append(e["testo"])
        elif tipo == "set_flag":
            stato.flags[e["nome"]] = e.get("valore", True)
        elif tipo == "modifica_salute":
            stato.salute = max(0, min(stato.salute_max, stato.salute + e["valore"]))
        elif tipo == "modifica_variabile":
            stato.variabili[e["nome"]] = stato.variabili.get(e["nome"], 0) + e["valore"]
        elif tipo == "modifica_variabile_set":
            stato.variabili[e["nome"]] = e["valore"]
        elif tipo == "rivela_oggetto":
            if e["oggetto"] not in stato.rivelati.get(stato.stanza, []):
                stato.rivelati.setdefault(stato.stanza, []).append(e["oggetto"])
        elif tipo == "nascondi_oggetto":
            # Lo rimuoviamo dai visibili e dai rivelati (in modo un po' brutale ma efficace)
            if e["oggetto"] in stato.rivelati.get(stato.stanza, []):
                stato.rivelati[stato.stanza].remove(e["oggetto"])
            if "oggetti_visibili" in stato.ds and e["oggetto"] in stato.ds["oggetti_visibili"]:
                stato.ds["oggetti_visibili"].remove(e["oggetto"])
        elif tipo == "aggiungi_oggetto_inv":
            if e["oggetto"] not in stato.inv:
                stato.inv.append(e["oggetto"])
        elif tipo == "rimuovi_oggetto":
            if e["oggetto"] in stato.inv:
                stato.inv.remove(e["oggetto"])
            # Rimuove anche dalla stanza se è lì
            if e["oggetto"] in stato.rivelati.get(stato.stanza, []):
                 stato.rivelati[stato.stanza].remove(e["oggetto"])
        elif tipo == "sblocca_uscita":
            stato.uscite_sbloccate.setdefault(stato.stanza, []).append(e["direzione"].upper())
        elif tipo == "sposta_giocatore":
            stato.stanza = e["destinazione"]
            stato.t_stanza[stato.stanza] = 0 # Appena entra è 0 (diventa 1 a fine ciclo)
        elif tipo == "muori":
            stato.salute = 0
        elif tipo == "vittoria":
            stato.flags["Finale"] = True
            
    return "\n".join(msg_out)


def processa_eventi(stato: Stato) -> str:
    """Verifica e lancia eventi automatici di fine turno per la stanza corrente."""
    msg =[]
    for evento in stato.ds.get("eventi",[]):
        if evento.get("trigger") == "on_turn":
            if valuta_condizioni(stato, evento.get("condizioni",[])):
                res = esegui_effetti(stato, evento.get("effetti",[]))
                if res: msg.append(res)
    return "\n".join(msg)


def valuta_interazione(stato: Stato, interazioni: List[Dict], comando: str, id_strumento: str = None) -> Optional[str]:
    """Cerca un'interazione valida in un elenco e la esegue."""
    for inter in interazioni:
        if inter["comando"] == comando:
            # Se l'interazione richiede uno strumento, verifica che combaci
            richiede_strum = inter.get("strumento")
            richiede_target = inter.get("target")
            
            if richiede_strum and richiede_strum != id_strumento: continue
            if richiede_target and richiede_target != id_strumento: continue # se usato inverso

            if valuta_condizioni(stato, inter.get("condizioni",[])):
                return esegui_effetti(stato, inter.get("effetti",[]))
            elif "errore" in inter and inter["errore"]:
                return inter["errore"]
    return None

# ═══════════════════════════════════════════════════════
#  CORE DEI COMANDI
# ═══════════════════════════════════════════════════════

def cmd_universale(stato: Stato, cmd: Dict) -> str:
    a = cmd.get("a", "esamina").lower()
    o_txt = cmd.get("o", "").strip()
    su_txt = cmd.get("su", "") or cmd.get("con", "") or cmd.get("dest", "") or cmd.get("in", "")
    d = cmd.get("d", "").upper()
    # --- FIX ROBUSTEZZA LLM ---
    # Se l'LLM ha messo la direzione in "o" invece che in "d" (es: {"a": "vai", "o": "est"})
    if a == "vai" and not d and o_txt:
        d = o_txt.upper()
    # --------------------------
    # 1. Comandi Base Indipendenti dagli oggetti
    if a == "vai":
        uscite = stato.uscite_disponibili()
        for u in uscite:
            if u["direzione"] == d:
                stato.prima_visita.add(u["destinazione"])
                stato.stanza = u["destinazione"]
                stato.t_stanza[stato.stanza] = 0
                return descrivi_stanza(stato)
        
        # Check se è bloccata
        for u in stato.ds.get("uscite", []):
            if u["direzione"] == d and u.get("bloccata", False):
                return u.get("messaggio_blocco", "È bloccata.")
        return f"Non puoi andare a {d}."
        
    if a in ("inventario", "i"):
        if not stato.inv: return "🎒 Il tuo inventario è vuoto."
        nomi = [stato.oggetti[idx]["nome"] for idx in stato.inv]
        return f"🎒 Stai portando: {' / '.join(nomi)}"
        
    if a in ("salute", "s"):
        barre = "█" * (stato.salute // 10)
        vuote = "░" * (10 - stato.salute // 10)
        return f"❤ Salute: {stato.salute}/{stato.salute_max}[{barre}{vuote}]"
        
    if a == "fuggi":
        return "Non c'è motivo di scappare, oppure non puoi farlo in questa direzione."

    # 2. Risoluzione Entità (Trova gli ID degli oggetti digitati)
    visibili = stato.oggetti_visibili_stanza()
    id_obj = stato.trova_id_oggetto(o_txt, visibili + stato.inv)
    id_su  = stato.trova_id_oggetto(su_txt, visibili + stato.inv) if su_txt else None

    # Se l'utente scrive "stanza" o un'azione generica senza oggetto
    if not o_txt or o_txt.lower() == "stanza" or (not id_obj and a in ("esamina", "guarda", "cerca", "riordina")):
        # Controlliamo prima se la stanza ha un'interazione specifica per questo comando a vuoto!
        res_stanza = valuta_interazione(stato, stato.ds.get("interazioni_stanza",[]), a)
        if res_stanza: return res_stanza
        
        if a in ("esamina", "guarda", "osserva"):
            return descrivi_stanza(stato)
        return f"Non sai come fare '{a}' qui."

    # Se non trova l'oggetto
    if not id_obj and kw_is_not_tutto(o_txt):
        return f"Non vedi '{o_txt}' qui."

    # 3. Comandi di Sistema (Prendi/Lascia)
    if a == "prendi":
        if o_txt.lower() == "tutto":
            presi, non_presi =[], []
            for v_id in list(visibili):
                obj = stato.oggetti[v_id]
                if obj.get("raccoglibile", False):
                    stato.inv.append(v_id)
                    presi.append(obj["nome"])
                else:
                    non_presi.append(obj["nome"])
            msg = ""
            if presi: msg += f"✓ Hai raccolto: {', '.join(presi)}.\n"
            if non_presi: msg += f"⚠ Non puoi raccogliere: {', '.join(non_presi)}."
            return msg.strip() or "Non c'è niente da prendere."
        
        obj = stato.oggetti[id_obj]
        
        # Check interazioni custom per "prendi" (Es. salsicce)
        res_custom = valuta_interazione(stato, obj.get("interazioni",[]), "prendi")
        if res_custom: return res_custom
        
        if not obj.get("raccoglibile", False): return f"Non puoi raccogliere {obj['nome']}."
        if id_obj in stato.inv: return "Lo hai già preso."
        stato.inv.append(id_obj)
        return f"✓ Raccogli {obj['nome']}."

    if a == "lascia":
        if not id_obj or id_obj not in stato.inv: return "Non hai questo oggetto."
        stato.inv.remove(id_obj)
        stato.rivelati.setdefault(stato.stanza, []).append(id_obj)
        return f"Lasci {stato.oggetti[id_obj]['nome']} sul pavimento."

    # 4. Azioni Generiche / Interazioni su Oggetti
    if id_obj:
        obj1 = stato.oggetti[id_obj]
        
        # A) Cerca interazione diretta sull'oggetto primario
        res = valuta_interazione(stato, obj1.get("interazioni",[]), a, id_su)
        if res: return res
        
        # B) Se c'è un target, cerca l'interazione sul target (es: "apri botola con chiave")
        if id_su:
            obj2 = stato.oggetti[id_su]
            res2 = valuta_interazione(stato, obj2.get("interazioni",[]), a, id_obj)
            if res2: return res2

    return f"L'azione '{a}' non produce alcun effetto su questo."

def kw_is_not_tutto(testo):
    return "tutto" not in testo.lower() and "ogni cosa" not in testo.lower()

# ═══════════════════════════════════════════════════════
#  DESCRIZIONE STANZA CON ATMOSFERA DINAMICA
# ═══════════════════════════════════════════════════════

def descrivi_stanza(stato: Stato, extra: str = "") -> str:
    ds = stato.ds
    nome = ds["nome"]
    atm = ds.get("atmosfera", "")
    
    # Aggiorna l'atmosfera dinamicamente leggendo dal JSON!
    for st_atm in ds.get("stati_atmosfera",[]):
        if valuta_condizioni(stato, [st_atm["condizione"]]):
            atm += " " + st_atm["testo"]
            
    uscite_nomi = [f"{u['direzione']}" for u in stato.uscite_disponibili()]
    oggetti = [stato.oggetti[o_id]["nome"] for o_id in stato.oggetti_visibili_stanza()]

    if USE_LLM:
        ctx = f"Stanza: {nome}. Atmosfera: {atm}\nOggetti: {', '.join(oggetti) or 'nessuno'}.\nUscite libere: {', '.join(uscite_nomi) or 'nessuna'}."
        if extra: ctx += f"\nEvento in corso: {extra}."
        ctx += f"\n\nLINGUA DI OUTPUT RICHIESTA: {stato.lingua.upper()}"
        res = llm_descrivi(ctx)
        if res: return f"[{nome}]\n{res}"

    # Fallback Testuale
    p = [f"[{nome}]", atm]
    if oggetti: p.append("Oggetti: " + ", ".join(oggetti))
    if uscite_nomi: p.append("Uscite: " + ", ".join(uscite_nomi))
    if extra: p.append(extra)
    return "\n".join(p)


# ═══════════════════════════════════════════════════════
#  GESTIONE FILE
# ═══════════════════════════════════════════════════════

def salva_partita(stato: Stato, filename: str = "gamestatus.json"):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(stato.esporta_dati(), f, indent=4)
        print(f"\n💾 Salvataggio completato in '{filename}'.")
    except Exception as e:
        print(f"\n❌ Errore salvataggio: {e}")

def carica_partita(stato: Stato, filename: str = "gamestatus.json") -> bool:
    if not os.path.exists(filename): return False
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            stato.importa_dati(json.load(f))
        return True
    except: return False


# ═══════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════

def main():
    hdr("UNIVERSAL TEXT ADVENTURE ENGINE")

    try:
        with open(DB_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except FileNotFoundError:
        print(f"\n❌ JSON Database '{DB_FILE}' non trovato.")
        sys.exit(1)

    stato = Stato(db)

    if USE_LLM: print(f"\n✓ Ollama Locale ({MODEL}) connesso.")
    else: print("\n⚠ Modalità Fallback (no-LLM).")
    
    if os.path.exists("gamestatus.json"):
        carica_partita(stato, "gamestatus.json")
        stampa(llm_traduci("[Caricamento Automatico] Partita ripresa!", stato.lingua))
        print()
        stampa(descrivi_stanza(stato))
        sep()
    else:
        stampa(llm_traduci("Ti risvegli nell'incubo...", stato.lingua))
        print()
        stato.prima_visita.add(stato.stanza)
        stampa(descrivi_stanza(stato))
        sep()

    while True:
        print()
        try: raw = input("▶  ").strip()
        except: break

        if not raw: continue
        raw_lower = raw.lower()
        
        if raw_lower == "save":
            salva_partita(stato); continue
        if raw_lower.startswith("load"):
            if carica_partita(stato): stampa(descrivi_stanza(stato))
            continue
        if raw_lower in ("exit", "quit", "q"):
            if input("Salvare? (s/n): ").lower() in ('s','y'): salva_partita(stato)
            break
        if raw_lower.startswith("language ") or raw_lower.startswith("lingua "):
            stato.lingua = raw.split(" ", 1)[1]
            print(f"[Language: {stato.lingua.upper()}]")
            stampa(descrivi_stanza(stato))
            continue

        # Parsing Universale
        # Se non c'è LLM, _fallback_parse è ancora vivo nello script? 
        # (Per brevità ho rimosso il fallback a keyword giganti, ci affidiamo al JSON)
        # comandi = llm_parse(stato, raw) or [{"a": "esamina", "o": "stanza"}]
        # Parsing Universale: Corsia preferenziale per i movimenti!
        if raw_lower in _DIREZIONI_RAPIDE:
            comandi =[{"a": "vai", "d": _DIREZIONI_RAPIDE[raw_lower]}]
        else:
            comandi = llm_parse(stato, raw) or[{"a": "esamina", "o": "stanza"}]
        for cmd in comandi:
            risposta = cmd_universale(stato, cmd)
            if risposta:
                print()
                stampa(llm_traduci(risposta, stato.lingua))

            if stato.morto() or stato.flags.get("Finale"): break

        if stato.morto():
            print(); sep("═"); stampa(llm_traduci("💀 GAME OVER.", stato.lingua)); sep("═")
            if os.path.exists("gamestatus.json"): os.remove("gamestatus.json")
            break

        if stato.flags.get("Finale"):
            print(); sep("═"); stampa(llm_traduci("✨ VITTORIA!", stato.lingua)); sep("═")
            if os.path.exists("gamestatus.json"): os.remove("gamestatus.json")
            break

        stato.turno += 1
        stato.t_stanza[stato.stanza] = stato.t_stanza.get(stato.stanza, 0) + 1

        msg_evento = processa_eventi(stato)
        if msg_evento:
            print()
            stampa(llm_traduci(f"⚡ {msg_evento}", stato.lingua))
            
        if stato.morto():
            print(); sep("═"); stampa(llm_traduci("💀 SEI MORTO.", stato.lingua)); sep("═")
            break

if __name__ == "__main__":
    main()