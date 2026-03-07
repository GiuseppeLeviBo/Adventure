#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║         LA CASA MALEDETTA  —  Avventura Testuale             ║
║   Engine Python + Ollama (Locale) per narrazione LLM         ║
╚══════════════════════════════════════════════════════════════╝

Uso:
    python avventura.py            → gioca con Ollama locale
    python avventura.py --no-llm   → solo testo statico

Requisiti:
    pip install requests
    Avere Ollama installato e un modello scaricato (es. llama3.2)

Il file database_mondo.json deve essere nella stessa cartella.
"""
from __future__ import annotations
import json
import os
import re
import sys
import textwrap
from typing import Dict, List, Optional, Set, Tuple

# ═══════════════════════════════════════════════════════
#  CONFIGURAZIONE OLLAMA (LOCALE)
# ═══════════════════════════════════════════════════════

# Inserisci qui il nome del modello che hai scaricato su Ollama
# (es: "llama3.2", "mistral", "qwen2.5", "gemma3:27b-cloud")
MODEL      = "gemma3:27b-cloud"   
OLLAMA_URL = "http://localhost:11434/api/chat"

DB_FILE  = os.path.join(os.path.dirname(__file__), "database_mondo.json")
USE_LLM  = ("--no-llm" not in sys.argv)
COL      = 82   # larghezza testo

# ═══════════════════════════════════════════════════════
#  UTILITY OUTPUT
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

# ═══════════════════════════════════════════════════════
#  CHIAMATE LLM  (OLLAMA LOCALE)
# ═══════════════════════════════════════════════════════

def _llm_call(system: str, user: str, max_tokens: int = 400) -> Optional[str]:
    """Chiamata generica all'API locale di Ollama."""
    if not USE_LLM:
        return None
    try:
        import requests
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages":[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "stream": False,  
                "options": {
                    "temperature": 0.7,
                    "num_predict": max_tokens  
                }
            },
            timeout=120, 
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    
    except requests.exceptions.ConnectionError:
        print("\n[DEBUG LLM] Impossibile connettersi a Ollama. Hai avviato l'applicazione Ollama?")
        return None
    except Exception as e:
        print(f"\n[DEBUG LLM OLLAMA ERROR] {e}")
        return None


_SYSTEM_NARRATORE = (
    "Sei il Game Master di un'avventura testuale dark fantasy/gotica degli anni '80. "
    "Il tuo compito è riscrivere la descrizione della stanza fornita per renderla estremamente immersiva e spaventosa (massimo 130 parole). "
    "REGOLE FONDAMENTALI: "
    "1. DEVI menzionare esplicitamente TUTTI gli oggetti visibili e TUTTE le uscite fornite. "
    "2. NON inventare uscite, nemici, porte o oggetti che non sono nell'elenco. "
    "3. Scrivi in seconda persona singolare (es: 'Senti il freddo che ti avvolge...'). "
    "4. TRADUZIONE: Devi scrivere l'intera risposta ESCLUSIVAMENTE nella lingua indicata dal prompt (es. se la lingua è 'english', scrivi in inglese mantenendo l'atmosfera)."
)

_SYSTEM_PARSER = """Sei il traduttore semantico di un'avventura testuale.
Riceverai l'input del giocatore e il contesto della stanza.
Il giocatore PUÒ SCRIVERE IN QUALSIASI LINGUA (inglese, francese, spagnolo, ecc.).
Il tuo compito è tradurre la sua intenzione in una LISTA JSON di azioni valide.

REGOLE FONDAMENTALI (TRADUZIONE INVERSA):
1. Il JSON in output DEVE essere sempre e solo in ITALIANO, perché il motore di gioco comprende solo l'italiano.
2. Traduci l'azione del giocatore nei verbi consentiti (es. se dice "take", usa "prendi"; se dice "open", usa "apri").
3. Mappa l'oggetto richiesto al nome ESATTO in italiano presente nel Contesto (es. se dice "grab the knife", e nel contesto c'è "Coltello da caccia", tu scriverai "Coltello da caccia").
4. Devi restituire SOLO un array JSON valido. Nessun testo descrittivo.

Formati JSON consentiti (sempre e solo con questi verbi in italiano!):
{"a":"vai",      "d":"NORD|SUD|EST|OVEST|SU|GIU"}
{"a":"prendi",   "o":"nome oggetto"}
{"a":"lascia",   "o":"nome oggetto"}
{"a":"esamina",  "o":"nome oggetto o 'stanza'"}
{"a":"usa",      "o":"nome oggetto", "su":"target"}
{"a":"apri",     "o":"nome oggetto", "con":"strumento"}
{"a":"leggi",    "o":"nome oggetto"}
{"a":"attacca",  "o":"nome nemico",  "con":"arma"}
{"a":"dai",      "o":"nome oggetto", "dest":"destinatario"}
{"a":"cerca",    "o":"dove/cosa"}
{"a":"sposta",   "o":"nome oggetto"}
{"a":"fuggi"}
{"a":"inventario"}
{"a":"salute"}
{"a":"aiuto"}
"""

def llm_descrivi(ctx: str) -> Optional[str]:
    if not USE_LLM:
        return None
    return _llm_call(_SYSTEM_NARRATORE, ctx, max_tokens=350)

def llm_parse(stato: 'Stato', inp: str) -> Optional[List[Dict]]:
    if not USE_LLM:
        return None
        
    oggetti_visibili = ", ".join(stato.oggetti_visibili_stanza()) or "nessuno"
    inventario = ", ".join(stato.inv) or "vuoto"
    
    user_prompt = (
        f"Contesto:\n"
        f"- Oggetti visibili: {oggetti_visibili}\n"
        f"- Nel tuo inventario: {inventario}\n\n"
        f"Input del giocatore: '{inp}'"
    )

    try:
        import requests
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "format": "json",
                "messages":[
                    {"role": "system", "content": _SYSTEM_PARSER},
                    {"role": "user",   "content": user_prompt},
                ],
                "stream": False,
                # Temperatura a ZERO: vogliamo un traduttore robotico, non creativo!
                "options": {"temperature": 0.0} 
            },
            timeout=20, 
        )
        r.raise_for_status()
        raw = r.json()["message"]["content"].strip()
        
        # 1. Pulizia brutale del Markdown (rimuove ```json e ```)
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        
        parsed = None
        
        # 2. Tenta di leggere il JSON
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # 3. Se fallisce, usa le Regex per "estrarre" a forza l'array o l'oggetto
            m = re.search(r'(\[.*?\]|\{.*?\})', raw, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(1))
                except:
                    pass
        
        # 4. Assicurati che restituisca sempre una lista di comandi
        if isinstance(parsed, dict):
            return [parsed]
        elif isinstance(parsed, list) and len(parsed) > 0 and "a" in parsed[0]:
            return parsed
            
    except Exception as e:
        # Se fallisce ancora, stampiamo il testo 'raw' per vedere cosa diavolo ha scritto l'LLM
        print(f"\n[DEBUG LLM PARSER] Errore di decodifica. L'LLM ha risposto questo:\n{raw if 'raw' in locals() else e}")
        
    return None

    if not USE_LLM:
        return None
        
    oggetti_visibili = ", ".join(stato.oggetti_visibili_stanza()) or "nessuno"
    inventario = ", ".join(stato.inv) or "vuoto"
    
    user_prompt = (
        f"Contesto:\n"
        f"- Oggetti visibili: {oggetti_visibili}\n"
        f"- Nel tuo inventario: {inventario}\n\n"
        f"Input del giocatore: '{inp}'"
    )

    try:
        import requests
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "format": "json",
                "messages":[
                    {"role": "system", "content": _SYSTEM_PARSER},
                    {"role": "user",   "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=20, 
        )
        r.raise_for_status()
        raw = r.json()["message"]["content"].strip()
        
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return [parsed]
        elif isinstance(parsed, list):
            return parsed
            
    except Exception as e:
        print(f"\n[DEBUG LLM PARSER ERROR] {e}")
        
    return None

# ═══════════════════════════════════════════════════════
#  PARSER DI FALLBACK (keyword-based)
# ═══════════════════════════════════════════════════════

_DIRS = {
    "nord": "NORD", "sud": "SUD", "est": "EST", "ovest": "OVEST",
    "su": "SU", "giù": "GIU", "giu": "GIU",
    "n": "NORD",            "e": "EST", "o": "OVEST",
}
def llm_traduci(testo: str, lingua: str) -> str:
    """Traduce i messaggi di sistema di Python nella lingua scelta dal giocatore."""
    if not USE_LLM or not testo:
        return testo
        
    # Se la lingua è italiano, non perdiamo tempo a chiamare l'LLM, restituiamo subito!
    if lingua.lower() in ("italiano", "it", "ita"):
        return testo

    system_prompt = (
        f"Sei il traduttore silente di un'avventura testuale. "
        f"Traduci la seguente frase in {lingua.upper()}. "
        f"REGOLE: "
        f"1. Mantieni ESATTAMENTE la formattazione originale e le emoji (es. ✓, ⚠, 🔲, 🔑, 🎒, 🔆). "
        f"2. Non aggiungere MAI spiegazioni, saluti o virgolette. Solo la pura traduzione."
    )

    try:
        import requests
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages":[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": testo},
                ],
                "stream": False,
                "options": {"temperature": 0.1} # Temperatura bassa per traduzione precisa
            },
            timeout=15, 
        )
        r.raise_for_status()
        raw = r.json()["message"]["content"].strip()
        # Pulizia estrema nel caso l'LLM chiacchieri lo stesso
        raw = re.sub(r'^(Here is|Sure|Ok|Okay|Translation:).*?\n', '', raw, flags=re.IGNORECASE).strip()
        return raw
    except Exception as e:
        # Se fallisce la traduzione, restituisce il testo originale in italiano
        return testo
def _fallback_parse(inp: str) -> Dict:
    t = inp.lower().strip()

    if t in ("i", "inv", "inventario"):         return {"a": "inventario"}
    if t in ("s", "salute", "hp", "vita"):      return {"a": "salute"}
    if t in ("h", "help", "aiuto", "?"):        return {"a": "aiuto"}
    if t == "fuggi":                            return {"a": "fuggi"}

    if t in _DIRS:
        return {"a": "vai", "d": _DIRS[t]}
    for k, v in _DIRS.items():
        if t.startswith(f"vai {k}") or t == k:
            return {"a": "vai", "d": v}

    prefissi =[
        ("prendi ",   "prendi"), ("raccogli ", "prendi"), ("afferra ",  "prendi"),
        ("lascia ",   "lascia"), ("posa ",     "lascia"), ("butta ",    "lascia"),
        ("esamina ",  "esamina"),("guarda ",   "esamina"),("osserva ",  "esamina"),
        ("leggi ",    "leggi"),
        ("apri ",     "apri"),
        ("usa ",      "usa"),    ("utilizza ", "usa"),    ("adopera ",  "usa"),
        ("attacca ",  "attacca"),("colpisci ", "attacca"),("combatti ", "attacca"),
        ("dai ",      "dai"),    ("offri ",    "dai"),
        ("cerca ",    "cerca"),  ("fruga ",    "cerca"),  ("ispeziona ","cerca"),
        ("sposta ",   "sposta"), ("muovi ",    "sposta"), ("spingi ",   "sposta"),
        ("ripara ",   "ripara"),
        ("riordina ", "riordina"),
        ("mescola ",  "mescola"),
        ("inserisci ","inserisci"),
        ("accendi ",  "accendi"),
        ("riempi ",   "riempi"),
    ]
    for pfx, azione in prefissi:
        if t.startswith(pfx):
            resto = t[len(pfx):].strip()
            cmd: Dict = {"a": azione, "o": resto}

            for sep_kw, key in[(" su ", "su"), (" con ", "con"),
                                  (" in ", "in"), (" a ", "dest")]:
                if sep_kw in resto:
                    parts = resto.split(sep_kw, 1)
                    cmd["o"]  = parts[0].strip()
                    cmd[key]  = parts[1].strip()
                    break

            if azione == "esamina" and cmd["o"] in (
                "stanza", "intorno", "qui", "tutto", "ambiente", ""
            ):
                cmd["o"] = "stanza"
            return cmd

    return {"a": "esamina", "o": "stanza"}


def parse_cmd(stato: 'Stato', inp: str) -> List[Dict]:
    """Prima prova l'LLM; se fallisce usa il parser basato su keyword."""
    parsed_list = llm_parse(stato, inp)
    if parsed_list:
        return parsed_list
    return [_fallback_parse(inp)]


# ═══════════════════════════════════════════════════════
#  STATO DI GIOCO
# ═══════════════════════════════════════════════════════

class Stato:
    def __init__(self, world: Dict, stanza_iniziale: str):
        self.world   = world
        self.stanza  = stanza_iniziale 
        self.salute  = 100
        self.inv: List[str] =[]
        self.flags:  Set[str] = set()
        self.turno   = 1
        self.t_stanza: Dict[str, int] = {self.stanza: 1}
        self.rivelati: Dict[str, Set[str]] = {}
        self.uscite_r: Dict[str, Set[str]] = {}
        self.raccolti: Set[str] = set()
        self.lingua              = "italiano"  # <--- Variabile per il multilingua!
        self.cassetta_aperta     = False
        self.tappeto_spostato    = False
        self.botola_vista        = False
        self.botola_aperta       = False
        self.lanterna_con_olio   = False
        self.lanterna_accesa     = False
        self.carne_osservata     = False
        self.zombi_comparso      = False
        self.zombi_vivo          = False
        self.tabernacolo_aperto  = False
        self.provetta_stato: Optional[str] = None
        self.lampada_posizionata = False
        self.salsicce            = 20
        self.borraccia_usi       = 3
        self.libro_falso_trovato = False
        self.volumi_riordinati   = False
        self.pergamena_letta     = False
        self.tende_aperte        = False
        self.prima_visita: Set[str] = set()
        self.scala_riparata      = False

    @property
    def ds(self) -> Dict:
        return self.world.get(self.stanza, {})

    def ts(self, s: Optional[str] = None) -> int:
        return self.t_stanza.get(s or self.stanza, 0)

    def morto(self) -> bool:
        return self.salute <= 0

    def ha(self, kw: str) -> bool:
        parole_chiave = kw.lower().split()
        for x in self.inv:
            if all(p in x.lower() for p in parole_chiave):
                return True
        return False

    def trova_inv(self, kw: str) -> Optional[str]:
        parole_chiave = kw.lower().split()
        for x in self.inv:
            if all(p in x.lower() for p in parole_chiave):
                return x
        return None
    def aggiungi(self, nome: str):
        if not self.ha(nome):
            self.inv.append(nome)

    def rimuovi_inv(self, kw: str):
        self.inv =[x for x in self.inv if kw.lower() not in x.lower()]

    def _chiave_raccolta(self, stanza: str, nome: str) -> str:
        return f"{stanza}|{nome}"

    def is_raccolta(self, nome: str, stanza: Optional[str] = None) -> bool:
        s = stanza or self.stanza
        return self._chiave_raccolta(s, nome) in self.raccolti

    def segna_raccolta(self, nome: str, stanza: Optional[str] = None):
        s = stanza or self.stanza
        self.raccolti.add(self._chiave_raccolta(s, nome))

    def oggetti_visibili_stanza(self, s: Optional[str] = None) -> List[str]:
        stanza = s or self.stanza
        dati = self.world.get(stanza, {})
        nomi: List[str] =[]
        for o in dati.get("oggetti", {}).get("visibili", []):
            if not self.is_raccolta(o["nome"], stanza):
                nomi.append(o["nome"])
        for nome in self.rivelati.get(stanza, set()):
            if not self.is_raccolta(nome, stanza):
                nomi.append(nome)
        return nomi

    def dati_oggetto_stanza(self, kw: str) -> Optional[Dict]:
        for cat in ("visibili", "nascosti"):
            for o in self.ds.get("oggetti", {}).get(cat,[]):
                if kw.lower() in o["nome"].lower():
                    return o
        return None

    def rivela_obj(self, nome: str, s: Optional[str] = None):
        k = s or self.stanza
        self.rivelati.setdefault(k, set()).add(nome)

    def rivela_uscita(self, direzione: str, s: Optional[str] = None):
        k = s or self.stanza
        self.uscite_r.setdefault(k, set()).add(direzione.upper())

    def uscite_disponibili(self) -> List[Dict]:
        result =[]
        for u in self.ds.get("uscite",[]):
            if u.get("nascosta"):
                if u["direzione"] in self.uscite_r.get(self.stanza, set()):
                    result.append(u)
            else:
                result.append(u)
        return result

    def avanza_turno(self):
        self.turno += 1
        self.t_stanza[self.stanza] = self.t_stanza.get(self.stanza, 0) + 1

    def entra_stanza(self, nome: str):
        self.stanza = nome
        self.t_stanza[nome] = self.t_stanza.get(nome, 0) + 1
# Aggiungi questi due metodi in fondo alla classe Stato:
    
    def esporta_dati(self) -> Dict:
        """Converte lo stato dinamico in un dizionario salvabile in JSON."""
        return {
            "stanza": self.stanza,
            "salute": self.salute,
            "inv": self.inv,
            "flags": list(self.flags),
            "turno": self.turno,
            "t_stanza": self.t_stanza,
            "rivelati": {k: list(v) for k, v in self.rivelati.items()},
            "uscite_r": {k: list(v) for k, v in self.uscite_r.items()},
            "raccolti": list(self.raccolti),
            "prima_visita": list(self.prima_visita),
            
            # Variabili di stato booleane/intere
            "cassetta_aperta": self.cassetta_aperta,
            "tappeto_spostato": self.tappeto_spostato,
            "botola_vista": self.botola_vista,
            "botola_aperta": self.botola_aperta,
            "lanterna_con_olio": self.lanterna_con_olio,
            "lanterna_accesa": self.lanterna_accesa,
            "carne_osservata": self.carne_osservata,
            "zombi_comparso": self.zombi_comparso,
            "zombi_vivo": self.zombi_vivo,
            "tabernacolo_aperto": self.tabernacolo_aperto,
            "provetta_stato": self.provetta_stato,
            "lampada_posizionata": self.lampada_posizionata,
            "salsicce": self.salsicce,
            "borraccia_usi": self.borraccia_usi,
            "libro_falso_trovato": self.libro_falso_trovato,
            "volumi_riordinati": self.volumi_riordinati,
            "pergamena_letta": self.pergamena_letta,
            "tende_aperte": self.tende_aperte,
            "scala_riparata": self.scala_riparata,
            
            "lingua": self.lingua, # <--- Aggiunta per i salvataggi!
        }
    def importa_dati(self, dati: Dict):
        """Ripristina lo stato dal dizionario JSON."""
        self.stanza = dati.get("stanza", self.stanza)
        self.salute = dati.get("salute", 100)
        self.inv = dati.get("inv",[])
        self.flags = set(dati.get("flags",[]))
        self.turno = dati.get("turno", 1)
        self.t_stanza = dati.get("t_stanza", {})
        self.rivelati = {k: set(v) for k, v in dati.get("rivelati", {}).items()}
        self.uscite_r = {k: set(v) for k, v in dati.get("uscite_r", {}).items()}
        self.raccolti = set(dati.get("raccolti",[]))
        self.prima_visita = set(dati.get("prima_visita",[]))
        self.lingua = dati.get("lingua", "Italiano")
        self.cassetta_aperta = dati.get("cassetta_aperta", False)
        self.tappeto_spostato = dati.get("tappeto_spostato", False)
        self.botola_vista = dati.get("botola_vista", False)
        self.botola_aperta = dati.get("botola_aperta", False)
        self.lanterna_con_olio = dati.get("lanterna_con_olio", False)
        self.lanterna_accesa = dati.get("lanterna_accesa", False)
        self.carne_osservata = dati.get("carne_osservata", False)
        self.zombi_comparso = dati.get("zombi_comparso", False)
        self.zombi_vivo = dati.get("zombi_vivo", False)
        self.tabernacolo_aperto = dati.get("tabernacolo_aperto", False)
        self.provetta_stato = dati.get("provetta_stato", None)
        self.lampada_posizionata = dati.get("lampada_posizionata", False)
        self.salsicce = dati.get("salsicce", 20)
        self.borraccia_usi = dati.get("borraccia_usi", 3)
        self.libro_falso_trovato = dati.get("libro_falso_trovato", False)
        self.volumi_riordinati = dati.get("volumi_riordinati", False)
        self.pergamena_letta = dati.get("pergamena_letta", False)
        self.tende_aperte = dati.get("tende_aperte", False)
        self.scala_riparata = dati.get("scala_riparata", False)

# ═══════════════════════════════════════════════════════
#  DESCRIZIONE STANZA
# ═══════════════════════════════════════════════════════

def descrivi_stanza(stato: 'Stato', extra: str = "") -> str:
    ds    = stato.ds
    nome  = ds.get("nome", stato.stanza)
    atm   = ds.get("atmosfera", "")
    
    # ── Override Dinamico dell'Atmosfera ──
    # Aggiorniamo il testo del JSON in base ai flags di Python prima di darlo all'LLM!
    
    if nome == "Maniero":
        if stato.lanterna_accesa:
            atm = atm.replace("lanterna spenta", "lanterna accesa che illumina a giorno l'atrio")
        if stato.tappeto_spostato:
            atm += " Il pesante tappeto cremisi è stato spinto di lato."
        if stato.botola_aperta:
            atm += " C'è una botola spalancata sul pavimento che scende nell'oscurità."
            
    elif nome == "Camera da letto":
        if stato.tende_aperte:
            atm = atm.replace("tende del baldacchino sono chiuse", "tende del baldacchino sono spalancate")
            
    elif nome == "Cancello Arrugginito":
        if stato.cassetta_aperta:
            atm += " Lo sportello della cassetta delle lettere scricchiola, ormai aperto."

    elif nome == "Laboratorio":
        if stato.lampada_posizionata:
            atm += " Una lampada a olio è posizionata vicino all'apparato."
    
    # ───────────────────────────────────────
    
    uscite_nomi =[
        f"{u['direzione']} → {u['destinazione']}"
        for u in stato.uscite_disponibili()
    ]
    oggetti = stato.oggetti_visibili_stanza()

    parti =[f"[{nome}]", atm]
    if oggetti:
        parti.append("Oggetti visibili: " + ", ".join(oggetti))
    if uscite_nomi:
        parti.append("Uscite: " + "  |  ".join(uscite_nomi))
    else:
        parti.append("Non vedi uscite ovvie.")
    if extra:
        parti.append(extra)
    testo_base = "  ".join(parti)

    if USE_LLM:
        ctx = (
            f"Stanza: {nome}. Atmosfera: {atm}. "
            f"Oggetti presenti e visibili: {', '.join(oggetti) if oggetti else 'nessuno'}. "
            f"Uscite possibili: {', '.join(uscite_nomi) if uscite_nomi else 'nessuna'}. "
        )
        if extra:
            ctx += f"Evento in corso: {extra}. "
            
        ctx += f"\n\nLINGUA DI OUTPUT RICHIESTA: {stato.lingua.upper()}" # <--- Aggiunto!
            
        versione_llm = llm_descrivi(ctx)
        if versione_llm:
            return f"[{nome}]\n{versione_llm}"

    return testo_base

# ═══════════════════════════════════════════════════════
#  EVENTI AUTOMATICI
# ═══════════════════════════════════════════════════════

def processa_eventi(stato: Stato) -> Tuple[str, bool]:
    msgs: List[str] =[]
    s  = stato.stanza
    ts = stato.ts()

    if s == "Palude Fangosa":
        if ts == 1:
            msgs.append("L'ambiente mette angoscia e oppressione.")
        elif ts == 2:
            msgs.append("⚠  I tuoi piedi cominciano ad affondare nel fango.")
        elif ts >= 3:
            stato.salute -= 10
            msgs.append(f"⚠  La palude ti inghiotte lentamente! −10 salute. (Salute: {stato.salute})")

    if s == "Giardino Nebbioso":
        if "Lupo Domato" not in stato.flags and "Lupo Morto" not in stato.flags:
            if ts == 1:
                msgs.append("In lontananza si sente l'abbaiare rabbioso di un cane.")
            elif ts == 2:
                msgs.append("⚠  Il latrato si avvicina, accompagnato da ringhi gutturali.")
            elif ts >= 3 and "Lupo in attacco" not in stato.flags:
                stato.flags.add("Lupo in attacco")
                msgs.append(
                    "🐺  Un Lupo Infernale emerge dalla nebbia e ti fissa con occhi rossi!\n"
                    "    → 'dai osso al lupo'  /  'attacca lupo con coltello'  /  Fuga = morte"
                )

    if s == "Sala da Pranzo" and not stato.zombi_comparso:
        if stato.carne_osservata or ts >= 2:
            stato.zombi_vivo    = True
            stato.zombi_comparso = True
            msgs.append(
                "☠  Un Servitore Zombi si trascina fuori da sotto il tavolo!\n"
                "    → 'attacca zombi con coltello'  /  'attacca zombi con candelabro'  /  'fuggi'"
            )

    if s == "Corridoio":
        if ts == 1:
            msgs.append("L'ambiente trasmette angoscia profonda.")
        elif ts == 2:
            msgs.append("⚠  Il cuore accelera. Le teche anatomiche sembrano osservarti.")
        elif ts >= 3:
            stato.salute -= 10
            msgs.append(
                f"⚠  Le creature nelle teche sembrano muoversi! Il terrore ti consuma. "
                f"−10 salute. (Salute: {stato.salute})"
            )

    if s == "Pozzo delle Ossa":
        stato.salute -= 10
        msgs.append(
            f"⚠  La putrefazione ti corrode i polmoni. −10 salute. (Salute: {stato.salute})"
        )

    game_over = stato.morto()
    return ("\n".join(msgs), game_over)

# ═══════════════════════════════════════════════════════
#  SALVATAGGIO / CARICAMENTO
# ═══════════════════════════════════════════════════════

def salva_partita(stato: Stato, filename: str = "gamestatus.json"):
    try:
        dati = stato.esporta_dati()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(dati, f, indent=4)
        print(f"\n💾 Salvataggio completato in '{filename}'.")
    except Exception as e:
        print(f"\n❌ Errore durante il salvataggio: {e}")

def carica_partita(stato: Stato, filename: str = "gamestatus.json") -> bool:
    if not os.path.exists(filename):
        print(f"\n❌ Nessun file di salvataggio '{filename}' trovato.")
        return False
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            dati = json.load(f)
        stato.importa_dati(dati)
        return True
    except Exception as e:
        print(f"\n❌ Errore durante il caricamento: {e}")
        return False
# ═══════════════════════════════════════════════════════
#  GESTORI DEI COMANDI
# ═══════════════════════════════════════════════════════

def cmd_vai(stato: Stato, direzione: str) -> str:
    d = direzione.upper()

    if stato.stanza == "Palude Fangosa" and d in ("NORD", "EST", "SUD"):
        return _esegui_entrata(stato, "Palude Fangosa")

    for u in stato.uscite_disponibili():
        if u["direzione"] != d:
            continue

        dest = u["destinazione"]
        cond = u.get("condizione", "")

        if dest == "Maniero" and "Chiave di Ferro" in cond:
            if not stato.ha("Chiave di Ferro"):
                return "⚠  Il cancello è sbarrato. Hai bisogno di una chiave robusta."

        if dest == "Cantina Umida" and not stato.botola_aperta:
            return "⚠  La botola è chiusa. Devi aprirla prima."

        if dest == "Corridoio" and not stato.scala_riparata:
            if stato.ha("Assi di legno") and stato.ha("Martello"):
                stato.scala_riparata = True
                stato.flags.add("Scala riparata")
                return (
                    "🔨  Usi gli assi e il martello per riparare i gradini fracassati. "
                    "La scala regge.\n" + _esegui_entrata(stato, dest)
                )
            else:
                stato.salute = 0
                return (
                    "💀  La scala cede sotto di te nel momento peggiore. "
                    "Precipiti nel vuoto. GAME OVER."
                )

        return _esegui_entrata(stato, dest)

    return f"Non c'è un'uscita verso {d} da qui."

def _esegui_entrata(stato: Stato, dest: str) -> str:
    prima_volta = dest not in stato.prima_visita
    stato.prima_visita.add(dest)
    stato.entra_stanza(dest)
    desc = descrivi_stanza(stato)
    sep()
    if prima_volta:
        prologo = stato.world.get(dest, {}).get("prologo", "")
        if prologo:
            return f"\n{prologo}\n\n{desc}"
    return f"\n{desc}"

def cmd_prendi(stato: 'Stato', kw: str) -> str:
    s = stato.stanza
    
    # Salsicce
    if "salsiccia" in kw or "salsicce" in kw:
        if s == "CUCINA" and stato.salsicce > 0:
            stato.salsicce -= 1
            stato.salute = min(100, stato.salute + 10)
            return (
                f"🍖  Strappi una salsiccia dalla catena e la mangi sul momento. "
                f"+10 salute! (Salsicce rimaste: {stato.salsicce})"
            )
        return "Non c'è nessuna salsiccia qui."

    # Comando PRENDI TUTTO gestito in base ai DATI
    if kw == "tutto":
        presi = []
        non_presi =[]
        
        for nome in stato.oggetti_visibili_stanza():
            dati = stato.dati_oggetto_stanza(nome)
            if dati and dati.get("raccoglibile") is False:
                non_presi.append(nome)
            else:
                stato.aggiungi(nome)
                stato.segna_raccolta(nome)
                stato.rivelati.get(s, set()).discard(nome)
                presi.append(nome)
                
        msg = ""
        if presi:
            msg += f"✓  Hai raccolto: {', '.join(presi)}.\n"
        if non_presi:
            msg += f"⚠  Non puoi raccogliere: {', '.join(non_presi)}."
        
        if not presi and not non_presi:
            msg = "Non c'è niente da prendere qui."
            
        return msg.strip()

    # Raccogli un oggetto specifico con MATCHING ELASTICO
    # (Tutte le parole in kw devono essere presenti nel nome dell'oggetto)
    parole_chiave = kw.lower().split()
    
    for nome in stato.oggetti_visibili_stanza():
        nome_low = nome.lower()
        # Se TUTTE le parole cercate sono nel nome dell'oggetto...
        if all(p in nome_low for p in parole_chiave):
            dati = stato.dati_oggetto_stanza(nome)
            if dati and dati.get("raccoglibile") is False:
                return f"'{nome}' non è qualcosa che puoi raccogliere."
                
            stato.aggiungi(nome)
            stato.segna_raccolta(nome)
            stato.rivelati.get(s, set()).discard(nome)
            return f"✓  Raccogli {nome}."

    return f"Non vedi '{kw}' qui da raccogliere."

def cmd_lascia(stato: Stato, kw: str) -> str:
    n = stato.trova_inv(kw)
    if not n:
        return f"Non hai '{kw}' nell'inventario."
    stato.rimuovi_inv(kw)
    stato.rivela_obj(n)
    return f"Lasci {n} sul pavimento."

def cmd_esamina(stato: Stato, kw: str) -> str:
    if not kw or kw in ("stanza", "intorno", "qui", "tutto", "ambiente"):
        return descrivi_stanza(stato)

    for nome in stato.oggetti_visibili_stanza():
        if kw in nome.lower():
            dati = stato.dati_oggetto_stanza(nome)
            risposta = f"Esamini attentamente {nome}."
            if dati:
                if "descrizione" in dati:
                    risposta += f" {dati['descrizione']}"
                if "uso" in dati:
                    risposta += f"[Uso: {dati['uso']}]"
                if "azioni" in dati:
                    az = ", ".join(f"'{a['tipo']}'" for a in dati["azioni"])
                    risposta += f" Azioni possibili: {az}."
                if "meccanica" in dati:
                    risposta += f"[Meccanica: {dati['meccanica']}]"
            if "carne" in nome.lower() and stato.stanza == "Sala da Pranzo":
                stato.carne_osservata = True
                risposta += " Manca un pezzo… qualcosa sta ancora mangiando."
            return risposta

    if "tappeto" in kw and stato.stanza == "Maniero":
        return "Un pesante tappeto cremisi copre il pavimento. Potrebbe nascondere qualcosa."

    if "soffitto" in kw and stato.stanza == "Biblioteca Oscura":
        stato.entra_stanza("Pozzo delle Ossa")
        return (
            "😱  Alzi lo sguardo verso il soffitto a cassettoni. Senti un click meccanico "
            "sotto i piedi — un pannello cede!\n"
            "Precipiti nel POZZO DELLE OSSA."
        )

    if "foro" in kw and stato.stanza == "Pozzo delle Ossa":
        return (
            "Un foro circolare nella parete, abbastanza grande per un braccio. "
            "Qualcosa brilla vagamente all'interno. Sembra rischioso inserire il braccio... "
            "forse un oggetto sarebbe più sicuro."
        )

    n = stato.trova_inv(kw)
    if n:
        return f"Tiri fuori {n} e lo esamini. Potrebbe tornarti utile nel momento giusto."

    return f"Non vedi niente di particolare riguardo '{kw}'."

def cmd_usa(stato: Stato, kw: str, su: str = "") -> str:
    n = stato.trova_inv(kw)
    if not n:
        return f"Non hai '{kw}' nell'inventario."

    nl = n.lower()

    if "chiave di ferro" in nl:
        if stato.stanza == "Maniero":
            if stato.botola_vista:
                stato.botola_aperta = True
                stato.rivela_uscita("GIU")
                return "🔑  La Chiave di Ferro scatta nella serratura. La botola si apre — si intravedono gradini verso il basso."
            if "botola" in su:
                return "Prima devi trovare la botola. Hai visto un tappeto sospetto..."
        return "Inserisci la chiave ma non apre niente di utile qui."

    if "petrolio" in nl:
        if stato.stanza == "Maniero":
            stato.lanterna_con_olio = True
            stato.rimuovi_inv("petrolio")
            return "🔆  Versi il petrolio nella lanterna spenta. Ora manca solo una fiamma."
        return "Non c'è una lanterna da riempire qui."

    if "fiammifero" in nl:
        if stato.stanza == "Maniero":
            if not stato.lanterna_con_olio:
                stato.rimuovi_inv("fiammifero")
                return (
                    "🕯  Accendi il fiammifero… ma la lanterna è asciutta. "
                    "Il fiammifero brucia inutilmente tra le tue dita."
                )
            stato.lanterna_accesa = True
            stato.rimuovi_inv("fiammifero")
            stato.rivela_uscita("OVEST")
            return (
                "🔆  La fiamma prende vita! La lanterna illumina l'atrio. "
                "Una traccia di sangue scuro sul pavimento porta verso OVEST — "
                "una porta prima invisibile nella penombra si svela."
            )
        if stato.ha("Lampada a olio"):
            stato.flags.add("Lampada accesa")
            stato.rimuovi_inv("fiammifero")
            return "🔆  Accendi la Lampada a olio col fiammifero. Una luce calda si diffonde."
        return "Hai acceso il fiammifero. Non c'è niente da accendere."

    if "acciarino" in nl:
        if stato.ha("Lampada a olio"):
            stato.flags.add("Lampada accesa")
            return "🔆  Usi l'Acciarino d'oro per accendere la Lampada a olio."
        return "Non c'è niente da accendere con l'acciarino."

    if "osso carnoso" in nl and "Lupo in attacco" in stato.flags:
        stato.flags.add("Lupo Domato")
        stato.flags.discard("Lupo in attacco")
        stato.rimuovi_inv("osso")
        return (
            "🐺  Lanci l'osso al lupo. L'animale si blocca, lo annusa, poi comincia a rosicchiarlo. "
            "Scuote la coda lentamente. Il pericolo è scampato."
        )

    if ("coltello" in nl or "candelabro" in nl) and stato.zombi_vivo:
        stato.zombi_vivo = False
        stato.flags.add("Zombi Morto")
        stato.rivela_obj("Chiave d'Argento")
        return (
            f"⚔  Colpisci il Servitore Zombi con {n}! "
            "Crolla sul pavimento con un gemito rauco. "
            "Vicino alla sua mano cadente brilla una Chiave d'Argento."
        )

    if "argento" in nl and stato.stanza == "Retro della casa":
        stato.tabernacolo_aperto = True
        stato.rivela_obj("Lampada a olio")
        return (
            "🔑  La Chiave d'Argento entra perfettamente nel Tabernacolo. "
            "Lo sportello si apre rivelando una Lampada a olio."
        )

    if "ottone" in nl and stato.stanza == "Laboratorio":
        stato.rivela_obj("Provetta Vuota")
        return (
            "🔑  La Chiave d'Ottone apre la cassetta di legno. "
            "All'interno, avvolta in un panno di seta, c'è una Provetta Vuota."
        )

    if "borraccia" in nl:
        if stato.borraccia_usi > 0:
            stato.borraccia_usi -= 1
            stato.salute = min(100, stato.salute + 5)
            return (
                f"💧  Bevi un sorso d'acqua fresca. +5 salute! "
                f"(Usi rimasti: {stato.borraccia_usi})"
            )
        return "💧  La borraccia è completamente vuota."

    if "fluido attivato" in nl and stato.stanza == "Camera da letto":
        if not stato.tende_aperte:
            return "Prima devi aprire le tende del baldacchino."
        stato.flags.add("Finale")
        return _finale()

    if "lampada" in nl and stato.stanza == "Laboratorio":
        if "Lampada accesa" in stato.flags:
            stato.lampada_posizionata = True
            if stato.provetta_stato == "prismatica_inserita":
                return _completa_fluido(stato)
            return "🔆  Posizioni la lampada accesa accanto all'apparato. Aspetti che la luce attraversi il prisma."
        return "La lampada non è accesa. Accendila prima."

    if "osso" in nl and stato.stanza == "Pozzo delle Ossa" and "foro" in su:
        return cmd_inserisci(stato, kw, "foro")

    return f"Usi {n}. Non succede nulla di speciale."

def cmd_apri(stato: Stato, kw: str, con: str = "") -> str:
    if "cassetta" in kw and stato.stanza == "Cancello Arrugginito":
        if stato.cassetta_aperta:
            return "La cassetta è già aperta."
        stato.cassetta_aperta = True
        stato.rivela_obj("Lettera")
        return "📬  Apri la cassetta delle lettere scricchiolante. Dentro c'è una Lettera ingiallita!"

    if "tende" in kw or "baldacchino" in kw:
        if stato.stanza != "Camera da letto":
            return "Non ci sono tende qui."
        if stato.tende_aperte:
            return "Le tende sono già aperte."
        stato.tende_aperte = True
        stato.rivela_obj("La Dama di Pietra")
        return (
            "🎭  Apri lentamente le pesanti tende di velluto. "
            "Una figura seduta ti fissa con occhi di marmo: "
            "una donna bellissima, immobile come la morte stessa, "
            "con una rosa di pietra tra le dita."
        )

    if "botola" in kw and stato.stanza == "Maniero":
        if not stato.botola_vista:
            return "Non hai ancora trovato la botola. Cerca sotto il tappeto."
        if stato.botola_aperta:
            return "La botola è già aperta."
        conStr = con or ""
        if stato.ha("Chiave di Ferro") or "ferro" in conStr.lower():
            stato.botola_aperta = True
            stato.rivela_uscita("GIU")
            return "🔑  La Chiave di Ferro apre la botola. Gradini di pietra scendono nell'oscurità."
        return "La botola è chiusa a chiave. Serve una chiave robusta."

    if "tabernacolo" in kw and stato.stanza == "Retro della casa":
        conStr = con or ""
        if stato.ha("Chiave d'Argento") or "argento" in conStr.lower():
            return cmd_usa(stato, "argento")
        return "Il tabernacolo è sigillato. Servirà una chiave d'argento."

    if "cassetta" in kw and stato.stanza == "Laboratorio":
        conStr = con or ""
        if stato.ha("Chiave d'Ottone") or "ottone" in conStr.lower():
            return cmd_usa(stato, "ottone")
        return "La cassetta di legno è chiusa a chiave."

    return f"Non riesci ad aprire '{kw}'."

def cmd_leggi(stato: Stato, kw: str) -> str:
    if "lettera" in kw:
        if stato.ha("Lettera"):
            return (
                "📜  La lettera recita:\n"
                "    «Benvenuto Giocatore, la sorte ti ha portato in questo luogo.\n"
                "     Un aiuto sarà dato a chi lo chiede.\n"
                "     Se lo chiede prima di morire.»"
            )
        return "Non hai nessuna lettera."

    if "diario" in kw and stato.stanza == "Camera da letto":
        return (
            "📖  Diario — Giorno 412:\n"
            "    «La formula della Vita Minerale è completa, ma instabile.\n"
            "     Volevo donare l'immortalità della pietra ai miei cari per salvarli\n"
            "     dalla peste, ma ho creato un giardino di incubi. I loro occhi\n"
            "     mi fissano ancora attraverso la nebbia.\n"
            "     Ho sigillato la cura nel laboratorio; la chiave è dove la cultura\n"
            "     è custodita. Ogni cosa al suo posto.\n"
            "     Chi guarda troppo in alto cadrà in basso.\n"
            "     La trappola protegge dagli ambiziosi.»"
        )

    if "pergamena" in kw:
        if stato.ha("Pergamena Ingiallita"):
            stato.pergamena_letta = True
            return (
                "📜  La pergamena descrive l'ordine esatto dei testi sugli scaffali.\n"
                "    Una frase è sottolineata in rosso:\n"
                "    «Il passaggio si apre quando ogni libro è al suo posto.»\n"
                "    (Usa 'riordina volumi' nella Biblioteca per procedere.)"
            )
        return "Non hai la Pergamena Ingiallita."

    return f"Non riesci a leggere '{kw}' oppure non ce l'hai."

def cmd_attacca(stato: Stato, nemico: str, con_arma: str = "") -> str:
    if "lupo" in nemico:
        if "Lupo in attacco" not in stato.flags:
            return "Non c'è nessun lupo da attaccare qui."
        arma = stato.trova_inv(con_arma) if con_arma else stato.trova_inv("coltello")
        if arma and "coltello" in arma.lower():
            stato.flags.add("Lupo Morto")
            stato.flags.discard("Lupo in attacco")
            stato.salute = max(0, stato.salute - 50)
            return (
                f"⚔  Ti getti sul Lupo Infernale con {arma}! Una lotta brutale. "
                f"Alla fine il lupo cade, ma ha lasciato segni profondi. −50 salute. "
                f"(Salute: {stato.salute})"
            )
        stato.salute = 0
        return "💀  Tenti di combattere il Lupo Infernale a mani nude. Ti sbrana. GAME OVER."

    if "zombi" in nemico or "servitore" in nemico:
        if not stato.zombi_vivo:
            return "Non c'è nessuno zombi da combattere."
        arma = stato.trova_inv(con_arma) if con_arma else (
            stato.trova_inv("coltello") or stato.trova_inv("candelabro")
        )
        if arma and ("coltello" in arma.lower() or "candelabro" in arma.lower()):
            return cmd_usa(stato, arma.split()[0].lower(), "zombi")
        stato.salute = max(0, stato.salute - 30)
        return (
            f"👊  Colpisci lo zombi a mani nude — senza troppo effetto. "
            f"−30 salute! (Salute: {stato.salute})\n"
            "    Hai un'arma? Usala!"
        )

    return f"Non c'è nessun '{nemico}' da attaccare qui."

def cmd_dai(stato: Stato, kw: str, dest: str = "") -> str:
    if "osso" in kw and ("lupo" in dest or "Lupo in attacco" in stato.flags):
        return cmd_usa(stato, "osso carnoso")
    n = stato.trova_inv(kw)
    if not n:
        return f"Non hai '{kw}'."
    if not dest:
        return f"A chi vuoi dare {n}?"
    return f"Offri {n} a {dest}, ma non sembra interessato."

def cmd_cerca(stato: Stato, kw: str) -> str:
    s = stato.stanza
    if ("attrezzi" in kw or "strumenti" in kw) and s == "Capanno Marcescente":
        stato.rivela_obj("Chiave di Ferro")
        stato.rivela_obj("Petrolio per lanterne")
        stato.rivela_obj("Scatola con un fiammifero")
        return (
            "🔍  Rovisti tra gli attrezzi arrugginiti. "
            "Trovi una Chiave di Ferro ingrigita, "
            "una bottiglia di Petrolio per lanterne, "
            "e una Scatola di fiammiferi con ancora un fiammifero dentro!"
        )

    if ("libri" in kw or "scaffali" in kw or "libro" in kw or "scaffale" in kw) and s == "Biblioteca Oscura":
        stato.libro_falso_trovato = True
        stato.rivela_obj("Chiave d'Ottone")
        stato.rivela_obj("Pergamena Ingiallita")
        return (
            "🔍  Scorri i dorsi di centinaia di volumi. Uno suona vuoto — "
            "è un libro falso! Dentro c'è una Chiave d'Ottone lucida. "
            "Più in fondo, tra fogli slegati, trovi anche una Pergamena Ingiallita."
        )

    if "tappeto" in kw and s == "Maniero":
        return cmd_sposta(stato, "tappeto")

    return "🔍  Cerchi attentamente, ma non trovi nulla di particolare."

def cmd_sposta(stato: Stato, kw: str) -> str:
    if "tappeto" in kw and stato.stanza == "Maniero":
        if stato.tappeto_spostato:
            return "Hai già spostato il tappeto. La botola è lì sotto."
        stato.tappeto_spostato = True
        stato.botola_vista = True
        return (
            "🔲  Trascini il pesante tappeto cremisi da parte. "
            "Sotto c'è una botola con una serratura arrugginita!\n"
            "    → 'apri botola con chiave di ferro'"
        )
    return f"Non riesci a spostare '{kw}'."

def cmd_ripara(stato: Stato, kw: str) -> str:
    if "scala" in kw and stato.stanza == "Scalinata":
        if stato.ha("Assi di legno") and stato.ha("Martello"):
            stato.scala_riparata = True
            stato.flags.add("Scala riparata")
            return "🔨  Inchioди gli assi di legno ai gradini rotti. La scala è percorribile!"
        return "Ti servono degli Assi di legno e un Martello."
    return f"Non sai come riparare '{kw}' qui."

def cmd_riempi(stato: Stato, kw: str, con: str = "") -> str:
    if "borraccia" in kw:
        if stato.stanza in ("CUCINA", "Retro della casa"):
            stato.borraccia_usi = 3
            return "💧  Riempi la borraccia. 3 usi disponibili."
        return "Non c'è una fonte d'acqua qui."
    if "lanterna" in kw:
        if stato.ha("Petrolio per lanterne"):
            return cmd_usa(stato, "petrolio")
        return "Non hai del petrolio."
    return f"Non sai come riempire '{kw}'."

def cmd_inserisci(stato: Stato, kw: str, dove: str) -> str:
    if "osso" in kw and "foro" in dove and stato.stanza == "Pozzo delle Ossa":
        osso = stato.trova_inv("osso") or (
            "Ossa" if "Ossa" in stato.oggetti_visibili_stanza() else None
        )
        if not osso:
            return "Non hai un osso adatto."
        if osso not in stato.inv:
            stato.aggiungi(osso)
            stato.segna_raccolta(osso)
        stato.rimuovi_inv("osso")
        stato.rivela_uscita("EST")
        return (
            "🦴  Inserisci con cautela l'osso nel foro. "
            "Un meccanismo scricchiola — la parete di pietra scivola verso est "
            "rivelando un passaggio stretto!"
        )

    if "braccio" in kw and "foro" in dove and stato.stanza == "Pozzo delle Ossa":
        stato.salute = 0
        return "💀  Infili il braccio nel foro. Una lama scatta nell'oscurità. GAME OVER."

    if "provetta" in kw and "foro" in dove and stato.stanza == "Laboratorio":
        if stato.ha("Provetta") and stato.provetta_stato == "mista":
            stato.provetta_stato = "prismatica_inserita"
            if stato.lampada_posizionata and "Lampada accesa" in stato.flags:
                return _completa_fluido(stato)
            return (
                "⚗  Inserisci la Provetta nel foro prismatico. "
                "Ora posiziona la Lampada a olio accesa accanto all'apparato."
            )
        if stato.ha("Provetta") and stato.provetta_stato == "fluido":
            return "Prima mescola il fluido con l'acqua della borraccia."
        if stato.ha("Provetta"):
            return "La provetta è vuota. Prima raccoglici il fluido blu."
        return "Non hai nessuna provetta."

    return f"Non sai come inserire '{kw}' in '{dove}' qui."

def cmd_mescola(stato: Stato, o1: str, o2: str) -> str:
    a, b = o1.lower(), o2.lower()
    ha_fluido  = ("fluido" in a or "fluido" in b)
    ha_acqua   = ("borraccia" in a or "acqua" in a or "borraccia" in b or "acqua" in b)

    if ha_fluido and ha_acqua and stato.stanza == "Laboratorio":
        if not stato.ha("Provetta"):
            return "Ti serve una Provetta Vuota."
        if stato.provetta_stato != "fluido":
            return "Prima raccogli il fluido blu nella provetta."
        if stato.borraccia_usi <= 0:
            return "La borraccia è vuota. Riempila prima."
        stato.borraccia_usi -= 1
        stato.provetta_stato = "mista"
        return (
            "⚗  Versi qualche goccia d'acqua dalla borraccia nella provetta col fluido. "
            "La miscela si fa cristallina e comincia a pulsare debolmente. "
            "La provetta è ora pronta per il foro prismatico."
        )

    return "Non sai come mescolare queste cose insieme."

def cmd_accendi(stato: Stato, kw: str, con: str = "") -> str:
    if "lampada" in kw or "lanterna" in kw:
        if stato.ha("Scatola con un fiammifero") or stato.ha("fiammifero"):
            return cmd_usa(stato, "fiammifero")
        if stato.ha("Acciarino d'oro") or stato.ha("acciarino"):
            return cmd_usa(stato, "acciarino")
        return "Non hai niente per fare fuoco."
    if stato.ha(kw):
        return cmd_usa(stato, kw, con)
    return f"Non hai '{kw}'."

def cmd_riordina(stato: Stato, kw: str) -> str:
    if ("volumi" in kw or "libri" in kw) and stato.stanza == "Biblioteca Oscura":
        if not stato.pergamena_letta:
            return (
                "Riordini qualche libro a caso, ma nulla accade. "
                "Forse una guida ti aiuterebbe... (hai la Pergamena Ingiallita?)"
            )
        if stato.volumi_riordinati:
            return "I volumi sono già al loro posto."
        stato.volumi_riordinati = True
        stato.rivela_uscita("NORD", "Biblioteca Oscura")
        return (
            "📚  Seguendo l'ordine indicato sulla pergamena, rimetti ogni tomo al suo posto. "
            "Un meccanismo ronza — una sezione della parete scivola via "
            "rivelando un passaggio verso NORD: il Laboratorio!"
        )
    return "Non sai come riordinare questo."

def cmd_raccogli_fluido(stato: Stato) -> str:
    if stato.stanza != "Laboratorio":
        return "Non c'è nessun fluido qui."
    if not stato.ha("Provetta"):
        return "Ti serve una Provetta Vuota per raccogliere il fluido."
    if stato.provetta_stato is not None:
        return "La provetta contiene già qualcosa."
    stato.provetta_stato = "fluido"
    return (
        "⚗  Avvicini la Provetta Vuota al fluido blu che gocciola dall'alambicco. "
        "La provetta si riempie di un liquido luminescente."
    )

def _completa_fluido(stato: Stato) -> str:
    stato.rimuovi_inv("Provetta")
    stato.provetta_stato = None
    stato.aggiungi("Provetta con Fluido Attivato")
    stato.flags.add("Fluido Attivato")
    return (
        "✨  La luce della Lampada attraversa la provetta prismatica. "
        "Un raggio dorato esplode nell'oscurità, la miscela pulsa e si stabilizza. "
        "Hai ottenuto la PROVETTA CON FLUIDO ATTIVATO!"
    )

def cmd_fuggi(stato: Stato) -> str:
    if stato.zombi_vivo and stato.stanza == "Sala da Pranzo":
        stato.zombi_vivo = False
        stato.zombi_comparso = False
        return cmd_vai(stato, "EST")
    if "Lupo in attacco" in stato.flags:
        stato.salute = 0
        return "💀  Tenti di scappare, ma il Lupo Infernale è più veloce. GAME OVER."
    return "Non c'è motivo urgente di fuggire in questo momento."

def cmd_inventario(stato: Stato) -> str:
    if not stato.inv:
        return "🎒  Il tuo inventario è vuoto."
    return "🎒  Stai portando: " + "  /  ".join(stato.inv)

def cmd_salute_cmd(stato: Stato) -> str:
    barre  = "█" * (stato.salute // 10)
    vuote  = "░" * (10 - stato.salute // 10)
    return f"❤  Salute: {stato.salute}/100   [{barre}{vuote}]"

def cmd_aiuto(_stato: Stato) -> str:
    return """
Comandi disponibili:
─────────────────────────────────────────────────────────────────────
  NORD / SUD / EST / OVEST / SU / GIU        muoviti
  PRENDI <oggetto>                            raccogli
  LASCIA <oggetto>                            posa a terra
  ESAMINA <oggetto | stanza>                  osserva
  USA <oggetto> [SU <target>]                 utilizza
  APRI <oggetto>[CON <strumento>]            apri
  LEGGI <oggetto>                             leggi
  ATTACCA <nemico> [CON <arma>]              combatti
  DAI <oggetto> A <destinatario>             offri
  CERCA <dove / cosa>                         fruga
  SPOSTA <oggetto>                            muovi un oggetto
  RIPARA <oggetto>                            ripara
  RIORDINA <cosa>                             riorganizza
  RIEMPI <oggetto> [CON <fonte>]              riempi
  INSERISCI <oggetto> IN <dove>              inserisci
  MESCOLA <oggetto> CON <altro>               mescola
  ACCENDI <oggetto>                           accendi
  FUGGI                                       scappa
  INVENTARIO  (o I)                          mostra oggetti
  SALUTE  (o S / HP)                         mostra vita
  AIUTO  (o ?)                               questo messaggio
  EXIT / QUIT                                esci
"""

# ═══════════════════════════════════════════════════════
#  ROUTING DEI COMANDI
# ═══════════════════════════════════════════════════════

def _pulisci_testo(testo: str) -> str:
    """Rimuove articoli comuni per facilitare il matching delle parole chiave."""
    if not testo:
        return ""
    t = " " + testo.lower().replace("'", " ") + " "
    articoli =[" il ", " lo ", " la ", " l ", " i ", " gli ", " le ", " un ", " uno ", " una "]
    for art in articoli:
        t = t.replace(art, " ")
    return t.strip()

def esegui_comando(stato: 'Stato', cmd: Dict) -> str:
    a   = cmd.get("a", "esamina").lower()
    o   = _pulisci_testo(cmd.get("o", ""))
    su  = _pulisci_testo(cmd.get("su", ""))
    d   = cmd.get("d", "").upper()
    con = _pulisci_testo(cmd.get("con", ""))
    dest = _pulisci_testo(cmd.get("dest", ""))
    _in  = _pulisci_testo(cmd.get("in", ""))

    # Se l'oggetto è vuoto e si vuole esaminare, di default guarda la stanza
    if not o and a in ("esamina", "guarda", "osserva"):
        o = "stanza"

    if stato.stanza == "Laboratorio":
        if a in ("prendi", "raccogli", "usa") and "fluido" in o:
            return cmd_raccogli_fluido(stato)
        if a == "mescola":
            return cmd_mescola(stato, o, con)
        if a == "inserisci" and "provetta" in o:
            return cmd_inserisci(stato, o, _in or "foro")
        if a in ("usa", "posiziona", "metti") and "lampada" in o:
            return cmd_usa(stato, "lampada")

    match a:
        case "vai": return cmd_vai(stato, d)
        case "prendi" | "raccogli": return cmd_prendi(stato, o)
        case "lascia" | "posa": return cmd_lascia(stato, o)
        case "esamina" | "guarda" | "osserva": return cmd_esamina(stato, o)
        case "usa" | "utilizza": return cmd_usa(stato, o, su or dest)
        case "apri": return cmd_apri(stato, o, con)
        case "leggi": return cmd_leggi(stato, o)
        case "attacca" | "colpisci" | "combatti": return cmd_attacca(stato, o, con)
        case "dai" | "offri": return cmd_dai(stato, o, dest)
        case "cerca" | "fruga": return cmd_cerca(stato, o)
        case "sposta" | "muovi" | "spingi": return cmd_sposta(stato, o)
        case "ripara": return cmd_ripara(stato, o)
        case "riordina": return cmd_riordina(stato, o)
        case "riempi": return cmd_riempi(stato, o, con)
        case "inserisci": return cmd_inserisci(stato, o, _in)
        case "mescola": return cmd_mescola(stato, o, con)
        case "accendi": return cmd_accendi(stato, o, con)
        case "fuggi": return cmd_fuggi(stato)
        case "inventario": return cmd_inventario(stato)
        case "salute": return cmd_salute_cmd(stato)
        case "aiuto": return cmd_aiuto(stato)
        case _: return cmd_esamina(stato, o)

# ═══════════════════════════════════════════════════════
#  FINALE
# ═══════════════════════════════════════════════════════

def _finale() -> str:
    sep("═")
    testo = (
        "\n✨  F I N A L E  ✨\n\n"
        "Versi con mano tremante il Fluido Attivato sulla Dama di Pietra.\n\n"
        "Un silenzio totale cade sulla stanza.\n\n"
        "Poi — un fremito. Le dita di pietra si schiudono lentamente.\n"
        "Il grigio abbandona la pelle. Gli occhi si aprono: umani, vivi, confusi.\n\n"
        "Un respiro profondo riecheggia nel silenzio della casa.\n\n"
        "Dal giardino arrivano altri suoni: il crepitio della pietra che si spezza,\n"
        "voci sommesse come di chi si sveglia da un sonno eterno.\n\n"
        "Statua dopo statua, i cari dello scienziato tornano in vita.\n"
        "Il giardino di incubi diventa un giardino di lacrime e abbracci.\n\n"
        "Hai spezzato la maledizione della Casa Maledetta.\n"
        "Dove il tuo antenato aveva fallito, tu hai avuto successo.\n\n"
        "                ════  F I N E  ════\n"
    )
    sep("═")
    return testo

# ═══════════════════════════════════════════════════════
#  CARICAMENTO MONDO
# ═══════════════════════════════════════════════════════

def carica_mondo(percorso: str) -> Tuple[Dict, str]:
    with open(percorso, encoding="utf-8") as f:
        lista = json.load(f)
    world = {s["nome"]: s for s in lista}
    stanza_iniziale = lista[0]["nome"] 
    return world, stanza_iniziale

# ═══════════════════════════════════════════════════════
#  LOOP PRINCIPALE
# ═══════════════════════════════════════════════════════

def main():
    hdr("LA CASA MALEDETTA  —  Avventura Testuale")

    try:
        world, stanza_iniziale = carica_mondo(DB_FILE)
    except FileNotFoundError:
        print(f"\n❌  File '{DB_FILE}' non trovato.")
        sys.exit(1)

    stato = Stato(world, stanza_iniziale)

    if not USE_LLM:
        print("\n⚠   Modalità senza LLM attiva (fallback statico).")
    else:
        print(f"\n✓  Ollama Locale pronto. Modello in uso: {MODEL}")
    print()

    # ── LOGICA DI AUTO-LOAD ALL'AVVIO ──
    if os.path.exists("gamestatus.json"):
        carica_partita(stato, "gamestatus.json")
        print("\n[Caricamento Automatico] Partita ripresa dall'ultimo salvataggio!\n")
        stampa(descrivi_stanza(stato))
        sep()
    else:
        # Avvio Nuova Partita
        prologo = world.get(stanza_iniziale, {}).get("prologo", "")
        stampa(prologo)
        print()
        stato.prima_visita.add(stanza_iniziale)
        sep()
        stampa(descrivi_stanza(stato))
        sep()

    # ── GAME LOOP ──
    while True:
        print()
        try:
            raw = input("▶  ").strip()
        except (EOFError, KeyboardInterrupt):
            # CTRL+Z o CTRL+C: Uscita brutale senza salvare
            print("\nChiusura improvvisa. La casa ti ha inghiottito...")
            break

        if not raw:
            continue
            
        raw_lower = raw.lower()
        
        # ── INTERCETTAZIONE META-COMANDI (SAVE/LOAD/EXIT) ──
        if raw_lower == "save":
            salva_partita(stato)
            continue
            
        if raw_lower.startswith("load"):
            parti = raw.split()
            # Permette 'load' o 'load nomesalvataggio.json'
            fname = parti[1] if len(parti) > 1 else "gamestatus.json"
            if carica_partita(stato, fname):
                print("\n[Partita Caricata con Successo]\n")
                stampa(descrivi_stanza(stato))
                sep()
            continue
        # --- NUOVO COMANDO LINGUA ---
        if raw_lower.startswith("language ") or raw_lower.startswith("lingua "):
            nuova_lingua = raw.split(" ", 1)[1]
            stato.lingua = nuova_lingua
            print(f"\n[Sistema] Lingua impostata su: {nuova_lingua.upper()}")
            # Ristampa la stanza tradotta!
            stampa(descrivi_stanza(stato))
            sep()
            continue
        # ----------------------------            
        if raw_lower in ("exit", "quit", "esci", "q"):
            risp = input("\nVuoi salvare la partita prima di uscire? (s/n): ").strip().lower()
            if risp in ('s', 'si', 'y', 'yes'):
                salva_partita(stato)
            print("\nAbbandoni la Casa Maledetta. Il mistero rimane.")
            break

        # ── PARSING ED ESECUZIONE NORMALE ──
        # Passiamo lo 'stato' al parser così l'LLM ha il contesto!
        comandi = parse_cmd(stato, raw)
        
        # Eseguiamo tutti i comandi generati in sequenza
        for cmd in comandi:
            risposta = esegui_comando(stato, cmd)
            if risposta:
                print()
                # TRADUCIAMO LA RISPOSTA DI PYTHON AL VOLO!
                risposta_tradotta = llm_traduci(risposta, stato.lingua)
                stampa(risposta_tradotta)

            # Trigger Biblioteca Oscura
            if (
                stato.stanza == "Biblioteca Oscura"
                and stato.pergamena_letta
                and stato.libro_falso_trovato
                and not stato.volumi_riordinati
                and cmd.get("a") in ("riordina", "usa", "sposta", "metti")
            ):
                ris = cmd_riordina(stato, "volumi")
                if "Laboratorio" in ris:
                    print()
                    stampa(llm_traduci(ris, stato.lingua))
                
            # Se muori o vinci durante la sequenza, interrompila
            if stato.morto() or "Finale" in stato.flags:
                break
        # ── CONTROLLO FINE GIOCO ──
        if stato.morto():
            print()
            sep("═")
            stampa("💀  GAME OVER — La tua storia finisce qui, nell'oscurità eterna.")
            sep("═")
            # Elimina il salvataggio automatico alla morte per impedire cheat/softlock!
            if os.path.exists("gamestatus.json"):
                os.remove("gamestatus.json")
            break

        if "Finale" in stato.flags:
            if os.path.exists("gamestatus.json"):
                os.remove("gamestatus.json")
            break

        # ── EVENTI E TURNI ──
        stato.avanza_turno()

        msg_evento, game_over = processa_eventi(stato)

        if msg_evento:
            print()
            # TRADUCIAMO ANCHE GLI EVENTI (es. Il latrato del lupo o il danno)
            stampa(llm_traduci(f"⚡  {msg_evento}", stato.lingua))
        if game_over:
            print()
            sep("═")
            stampa("💀  GAME OVER — Soccombono anche i più coraggiosi.")
            sep("═")
            if os.path.exists("gamestatus.json"):
                os.remove("gamestatus.json")
            break

if __name__ == "__main__":
    main()