#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL TEXT ADVENTURE ENGINE (Data-Driven) - v2
Patch conservative su regressioni introdotte nel refactor data-driven.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import os
import re
import sys
import textwrap
from typing import Any, Dict, List, Optional, Set, Tuple

MODEL = "gemma3:27b-cloud"
OLLAMA_URL = "http://localhost:11434/api/chat"

DB_FILE = os.path.join(os.path.dirname(__file__), "database_mondo_data_driven_v2.json")
USE_LLM = ("--no-llm" not in sys.argv)
COL = 82

_DIREZIONI_RAPIDE = {
    "n": "NORD", "s": "SUD", "e": "EST", "o": "OVEST",
    "nord": "NORD", "sud": "SUD", "est": "EST", "ovest": "OVEST",
    "su": "SU", "giu": "GIU", "giù": "GIU", "up": "SU", "down": "GIU",
}

_VIRTUAL_TOOLS = {
    "braccio": "braccio",
    "mano": "braccio",
    "arm": "braccio",
}

_CANONICAL_ACTIONS = (
    "vai", "prendi", "lascia", "esamina", "usa", "apri", "leggi", "attacca", "dai",
    "cerca", "sposta", "fuggi", "inventario", "salute", "aiuto", "inserisci",
    "mescola", "ripara", "riordina", "riempi", "accendi",
)

_DEFAULT_ACTION_FALLBACKS = {
    "riempi": ["usa"],
    "accendi": ["usa"],
}

_RELATION_SEPARATORS = [
    (" su ", "su"), (" con ", "con"), (" col ", "con"), (" coi ", "con"),
    (" in ", "in"), (" nel ", "in"), (" nello ", "in"), (" nella ", "in"),
    (" nei ", "in"), (" negli ", "in"), (" nelle ", "in"),
    (" a ", "dest"), (" al ", "dest"), (" allo ", "dest"), (" alla ", "dest"),
    (" ai ", "dest"), (" agli ", "dest"), (" alle ", "dest"),
]

# ===== Utility output =====
def wrap(t: str) -> str:
    return "\n".join(textwrap.fill(p, width=COL) for p in str(t).splitlines())


def stampa(t: str, prefisso: str = "") -> None:
    for riga in wrap(t).splitlines():
        print(prefisso + riga)


def sep(c: str = "-") -> None:
    print(c * COL)


def hdr(t: str) -> None:
    sep("=")
    print(f"  *  {t}")
    sep("=")


# ===== LLM =====
def _llm_call(
    system: str,
    user: str,
    max_tokens: int = 400,
    temp: float = 0.7,
    json_format: bool = False,
) -> Optional[str]:
    if not USE_LLM:
        return None

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temp, "num_predict": max_tokens},
    }
    if json_format:
        payload["format"] = "json"

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
    "REGOLE: menziona tutti gli oggetti/uscite forniti, non inventare, seconda persona, "
    "scrivi solo nella lingua richiesta."
)

_SYSTEM_PARSER = """Sei il traduttore semantico di un'avventura testuale.
Traduci l'input del giocatore (qualsiasi lingua) in JSON in ITALIANO.

REGOLE:
1) Solo JSON, nessun testo extra.
2) Usa i nomi oggetti del contesto.
3) Usa solo azioni canoniche: vai, prendi, lascia, esamina, usa, apri, leggi, attacca,
   dai, cerca, sposta, fuggi, inventario, salute, aiuto, inserisci, mescola,
   ripara, riordina, riempi, accendi.
4) Usa la sezione "Alias azioni" del contesto per mappare sinonimi alla forma canonica.
5) Se "prendi tutto", genera array di prendi per ogni oggetto visibile.
6) Rimuovi articoli non informativi (il/la/lo/l'/un/una...) nei campi o/su/con/dest/in.
"""


def llm_descrivi(ctx: str) -> Optional[str]:
    return _llm_call(_SYSTEM_NARRATORE, ctx, temp=0.7)


def llm_parse(stato: "Stato", inp: str) -> Optional[List[Dict[str, Any]]]:
    nomi_visibili = [stato.oggetti[id_obj]["nome"] for id_obj in stato.oggetti_visibili_stanza()]
    nomi_inv = [stato.oggetti[id_obj]["nome"] for id_obj in stato.inv if id_obj in stato.oggetti]

    alias_by_action: Dict[str, List[str]] = {}
    for alias, canon in stato.alias_azioni.items():
        alias_by_action.setdefault(canon, []).append(alias)

    alias_lines: List[str] = []
    for canon in sorted(alias_by_action.keys()):
        vals = sorted(set(alias_by_action[canon]))
        alias_lines.append(f"{canon}: {', '.join(vals[:14])}")

    ctx = (
        f"- Oggetti stanza: {', '.join(nomi_visibili) or 'nessuno'}\n"
        f"- Inventario: {', '.join(nomi_inv) or 'vuoto'}\n"
        f"- Alias azioni: {'; '.join(alias_lines)}"
    )
    user_prompt = f"Contesto:\n{ctx}\n\nInput giocatore: '{inp}'"


    raw = _llm_call(_SYSTEM_PARSER, user_prompt, temp=0.0, json_format=True)
    if not raw:
        return None

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
    except Exception:
        m = re.search(r"(\[.*?\]|\{.*?\})", raw, re.DOTALL)
        if not m:
            return None
        try:
            parsed = json.loads(m.group(1))
        except Exception:
            return None

    if isinstance(parsed, dict) and "a" in parsed:
        return [parsed]
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and "a" in parsed[0]:
        return parsed
    return None


# ===== Fallback parser =====
def _fallback_parse(stato: "Stato", inp: str) -> Dict[str, str]:
    t = inp.strip().lower()
    if not t:
        return {"a": "esamina", "o": "stanza"}

    if t in _DIREZIONI_RAPIDE:
        return {"a": "vai", "d": _DIREZIONI_RAPIDE[t]}

    parti = t.split(maxsplit=1)
    verbo = parti[0]
    resto = parti[1].strip() if len(parti) > 1 else ""

    azione = stato.alias_azioni.get(verbo)
    if not azione:
        return {"a": "esamina", "o": "stanza"}

    if azione == "vai":
        if resto:
            return {"a": "vai", "d": _DIREZIONI_RAPIDE.get(resto, resto.upper())}
        return {"a": "esamina", "o": "stanza"}

    cmd: Dict[str, str] = {"a": azione}
    if resto:
        cmd["o"] = resto

    for sep_kw, key in _RELATION_SEPARATORS:
        if sep_kw in resto:
            sx, dx = resto.split(sep_kw, 1)
            cmd["o"] = sx.strip()
            cmd[key] = dx.strip()
            break

    if azione in ("esamina", "cerca") and cmd.get("dest") and cmd.get("o", "") in ("sotto", "sopra", "dentro", "dietro", "vicino"):
        cmd["o"] = cmd.get("dest", "")
        cmd.pop("dest", None)

    if azione == "esamina" and cmd.get("o", "") in ("", "stanza", "intorno", "qui"):
        cmd["o"] = "stanza"

    return cmd


# ===== Stato =====
class Stato:
    def __init__(self, db: Dict[str, Any]):
        self.db = db
        self.stanze: Dict[str, Dict[str, Any]] = {s["id"]: s for s in db["stanze"]}
        self.oggetti: Dict[str, Dict[str, Any]] = {o["id"]: o for o in db["oggetti"]}

        cfg = db.get("configurazione", {})
        self.stanza = cfg.get("stanza_iniziale", list(self.stanze.keys())[0])
        self.salute_max = cfg.get("salute_max", 100)
        self.salute = self.salute_max
        self.variabili: Dict[str, Any] = dict(cfg.get("variabili_iniziali", {}))

        self.inv: List[str] = []
        self.flags: Dict[str, bool] = {}
        self.rivelati: Dict[str, List[str]] = {}
        self.uscite_sbloccate: Dict[str, List[str]] = {}
        self.oggetti_raccolti: Set[str] = set()

        self.turno = 1
        self.t_stanza: Dict[str, int] = {self.stanza: 1}
        self.prima_visita: Set[str] = set()
        self.lingua = "italiano"

        # Vocabolario azioni data-driven (alias -> azione canonica)
        self.alias_azioni: Dict[str, str] = {a: a for a in _CANONICAL_ACTIONS}
        cfg_alias = cfg.get("alias_azioni", {})
        if isinstance(cfg_alias, dict):
            for alias, canon in cfg_alias.items():
                if not isinstance(alias, str) or not isinstance(canon, str):
                    continue
                a = alias.strip().lower()
                c = canon.strip().lower()
                if a and c:
                    self.alias_azioni[a] = c

        # Garantisce che le azioni canoniche siano sempre disponibili.
        for a in _CANONICAL_ACTIONS:
            self.alias_azioni.setdefault(a, a)

        # Fallback azione data-driven (azione -> [azioni alternative])
        self.fallback_azioni: Dict[str, List[str]] = {
            k: list(v) for k, v in _DEFAULT_ACTION_FALLBACKS.items()
        }
        cfg_fallback = cfg.get("fallback_azioni", {})
        if isinstance(cfg_fallback, dict):
            for k, vals in cfg_fallback.items():
                if not isinstance(k, str):
                    continue
                base = self.alias_azioni.get(k.strip().lower(), k.strip().lower())
                if not isinstance(vals, list):
                    continue
                norm_vals: List[str] = []
                for v in vals:
                    if not isinstance(v, str):
                        continue
                    nv = self.alias_azioni.get(v.strip().lower(), v.strip().lower())
                    if nv and nv not in norm_vals:
                        norm_vals.append(nv)
                if norm_vals:
                    self.fallback_azioni[base] = norm_vals

        self.verbi_noti: Set[str] = set(self.alias_azioni.keys())

    @property
    def ds(self) -> Dict[str, Any]:
        return self.stanze[self.stanza]

    def ts(self, s: Optional[str] = None) -> int:
        return self.t_stanza.get(s or self.stanza, 0)

    def morto(self) -> bool:
        return self.salute <= 0

    def trova_id_oggetto(self, kw: str, liste_cerca: List[str]) -> Optional[str]:
        if not kw:
            return None

        def _tokens(t: str) -> List[str]:
            t = t.lower().replace("'", " ")
            t = re.sub(r"[^\w\s]", " ", t)
            stop = {
                "il", "lo", "la", "l", "i", "gli", "le", "un", "uno", "una",
                "del", "dello", "della", "dei", "degli", "delle", "di",
                "al", "allo", "alla", "ai", "agli", "alle", "a", "con", "su", "in",
            }
            out: List[str] = []
            for w in t.split():
                if not w or w in stop:
                    continue
                out.append(w)
            return out

        def _variants(w: str) -> Set[str]:
            v = {w}
            if len(w) > 4 and w[-1] in "aeiou":
                v.add(w[:-1])
            if len(w) > 5 and w.endswith(("one", "oni", "ale", "ali", "oso", "osa", "ivo", "iva")):
                v.add(w[:-3])
            if len(w) > 4:
                v.add(w[:4])
            return {x for x in v if x}

        def _score_token_match(q: str, n: str) -> float:
            if q == n:
                return 1.0
            if q in n or n in q:
                return 0.93

            qv = _variants(q)
            nv = _variants(n)
            if qv & nv:
                return 0.88

            return SequenceMatcher(None, q, n).ratio()

        parole = _tokens(kw)
        if not parole:
            return None

        strict_hits: List[Tuple[float, str]] = []
        fuzzy_best: Tuple[float, Optional[str]] = (0.0, None)

        for obj_id in liste_cerca:
            obj = self.oggetti.get(obj_id)
            if not obj:
                continue

            names: List[str] = [obj.get("nome", "")]
            aliases = obj.get("aliases", [])
            if isinstance(aliases, list):
                names.extend([a for a in aliases if isinstance(a, str)])

            name_tokens: List[str] = []
            for n in names:
                name_tokens.extend(_tokens(n))

            if not name_tokens:
                continue

            token_scores: List[float] = []
            all_match = True
            for q in parole:
                best_q = max(_score_token_match(q, nt) for nt in name_tokens)
                token_scores.append(best_q)
                if best_q < 0.78:
                    all_match = False

            avg_score = sum(token_scores) / len(token_scores)

            if all_match:
                strict_hits.append((avg_score, obj_id))
            elif len(parole) == 1 and avg_score > fuzzy_best[0]:
                fuzzy_best = (avg_score, obj_id)

        if strict_hits:
            strict_hits.sort(reverse=True)
            return strict_hits[0][1]

        if fuzzy_best[1] is not None and fuzzy_best[0] >= 0.82:
            return fuzzy_best[1]

        return None

    def oggetti_visibili_stanza(self, stanza_id: Optional[str] = None) -> List[str]:
        sid = stanza_id or self.stanza
        base = [o for o in self.stanze[sid].get("oggetti_visibili", []) if o not in self.oggetti_raccolti]
        dinamici = self.rivelati.get(sid, [])

        vis: List[str] = []
        for oid in base + dinamici:
            if oid in self.inv:
                continue
            if oid not in self.oggetti:
                continue
            if oid not in vis:
                vis.append(oid)
        return vis

    def uscite_disponibili(self) -> List[Dict[str, Any]]:
        uscite: List[Dict[str, Any]] = []
        sbloccate = set(self.uscite_sbloccate.get(self.stanza, []))

        for u in self.ds.get("uscite", []):
            if u.get("bloccata", False):
                flag_sblocco = u.get("sbloccata_da_flag")
                if (flag_sblocco and self.flags.get(flag_sblocco)) or (u["direzione"] in sbloccate):
                    uscite.append(u)
            else:
                uscite.append(u)

        return uscite

    def esporta_dati(self) -> Dict[str, Any]:
        return {
            "stanza": self.stanza,
            "salute": self.salute,
            "inv": self.inv,
            "flags": self.flags,
            "variabili": self.variabili,
            "turno": self.turno,
            "t_stanza": self.t_stanza,
            "rivelati": self.rivelati,
            "uscite_sbloccate": self.uscite_sbloccate,
            "prima_visita": list(self.prima_visita),
            "lingua": self.lingua,
            "oggetti_raccolti": sorted(self.oggetti_raccolti),
        }

    def importa_dati(self, d: Dict[str, Any]) -> None:
        self.stanza = d.get("stanza", self.stanza)
        self.salute = d.get("salute", self.salute_max)
        self.inv = list(d.get("inv", []))
        self.flags = dict(d.get("flags", {}))
        self.variabili = dict(d.get("variabili", {}))
        self.turno = d.get("turno", 1)
        self.t_stanza = dict(d.get("t_stanza", {}))
        self.rivelati = {k: list(v) for k, v in d.get("rivelati", {}).items()}
        self.uscite_sbloccate = {k: list(v) for k, v in d.get("uscite_sbloccate", {}).items()}
        self.prima_visita = set(d.get("prima_visita", []))
        self.lingua = d.get("lingua", "italiano")
        self.oggetti_raccolti = set(d.get("oggetti_raccolti", self.inv))


# ===== Rule engine =====
def valuta_condizioni(stato: Stato, condizioni: List[Dict[str, Any]]) -> bool:
    for c in condizioni:
        tipo = c.get("tipo")
        if tipo == "ha_oggetto":
            if c.get("oggetto") not in stato.inv:
                return False
        elif tipo == "flag_vero":
            if not stato.flags.get(c.get("nome"), False):
                return False
        elif tipo == "flag_falso":
            if stato.flags.get(c.get("nome"), False):
                return False
        elif tipo == "turni_stanza_uguale":
            if stato.ts() != c.get("valore"):
                return False
        elif tipo == "turni_stanza_maggior_uguale":
            if stato.ts() < c.get("valore"):
                return False
        elif tipo == "variabile_maggiore_di":
            if stato.variabili.get(c.get("nome"), 0) <= c.get("valore", 0):
                return False
        elif tipo == "stato_diverso":
            if stato.flags.get(c.get("valore"), False):
                return False
    return True


def _remove_from_all_revealed(stato: Stato, oggetto: str) -> None:
    for sid, arr in stato.rivelati.items():
        while oggetto in arr:
            arr.remove(oggetto)


def esegui_effetti(stato: Stato, effetti: List[Dict[str, Any]]) -> str:
    out: List[str] = []

    for e in effetti:
        tipo = e.get("tipo")

        if tipo == "messaggio":
            out.append(e.get("testo", ""))

        elif tipo == "set_flag":
            stato.flags[e["nome"]] = e.get("valore", True)

        elif tipo == "modifica_salute":
            delta = int(e.get("valore", 0))
            stato.salute = max(0, min(stato.salute_max, stato.salute + delta))

        elif tipo == "modifica_variabile":
            nome = e["nome"]
            stato.variabili[nome] = stato.variabili.get(nome, 0) + e.get("valore", 0)

        elif tipo == "modifica_variabile_set":
            stato.variabili[e["nome"]] = e.get("valore")

        elif tipo == "rivela_oggetto":
            oid = e.get("oggetto")
            if oid and oid not in stato.inv and oid in stato.oggetti:
                arr = stato.rivelati.setdefault(stato.stanza, [])
                if oid not in arr:
                    arr.append(oid)

        elif tipo == "nascondi_oggetto":
            oid = e.get("oggetto")
            if not oid:
                continue
            _remove_from_all_revealed(stato, oid)
            if oid in stato.ds.get("oggetti_visibili", []):
                stato.ds["oggetti_visibili"].remove(oid)

        elif tipo == "aggiungi_oggetto_inv":
            oid = e.get("oggetto")
            if oid and oid in stato.oggetti:
                if oid not in stato.inv:
                    stato.inv.append(oid)
                stato.oggetti_raccolti.add(oid)
                _remove_from_all_revealed(stato, oid)

        elif tipo == "rimuovi_oggetto":
            oid = e.get("oggetto")
            if not oid:
                continue
            while oid in stato.inv:
                stato.inv.remove(oid)
            _remove_from_all_revealed(stato, oid)

        elif tipo == "sblocca_uscita":
            direz = str(e.get("direzione", "")).upper()
            if direz:
                arr = stato.uscite_sbloccate.setdefault(stato.stanza, [])
                if direz not in arr:
                    arr.append(direz)

        elif tipo == "sposta_giocatore":
            dest = e.get("destinazione")
            if dest in stato.stanze:
                stato.stanza = dest
                stato.t_stanza[stato.stanza] = 0

        elif tipo == "muori":
            stato.salute = 0

        elif tipo == "vittoria":
            stato.flags["Finale"] = True

    return "\n".join([x for x in out if x])


def processa_eventi(stato: Stato) -> str:
    msg: List[str] = []
    for evento in stato.ds.get("eventi", []):
        if evento.get("trigger") != "on_turn":
            continue
        if not valuta_condizioni(stato, evento.get("condizioni", [])):
            continue
        res = esegui_effetti(stato, evento.get("effetti", []))
        if res:
            msg.append(res)
    return "\n".join(msg)


def _lista_interazioni(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def valuta_interazione(
    stato: Stato,
    interazioni: Any,
    comando: str,
    id_strumento: Optional[str] = None,
) -> Optional[str]:
    errore: Optional[str] = None
    trovato = False

    for inter in _lista_interazioni(interazioni):
        if inter.get("comando") != comando:
            continue

        trovato = True
        richiede_strum = inter.get("strumento")
        richiede_target = inter.get("target")

        if richiede_strum and richiede_strum != id_strumento:
            if not errore and inter.get("errore"):
                errore = inter["errore"]
            continue

        if richiede_target and richiede_target != id_strumento:
            if not errore and inter.get("errore"):
                errore = inter["errore"]
            continue

        if valuta_condizioni(stato, inter.get("condizioni", [])):
            return esegui_effetti(stato, inter.get("effetti", []))

        if not errore and inter.get("errore"):
            errore = inter["errore"]

    if trovato and errore:
        return errore
    return None


# ===== Commands =====
def _virtual_tool_id(testo: str) -> Optional[str]:
    if not testo:
        return None
    return _VIRTUAL_TOOLS.get(testo.strip().lower())


def cmd_aiuto() -> str:
    return (
        "Comandi: NORD/SUD/EST/OVEST/SU/GIU, VAI <dir>, PRENDI, LASCIA, ESAMINA, USA, "
        "APRI, LEGGI, ATTACCA, DAI, CERCA, SPOSTA, INSERISCI, MESCOLA, RIPARA, RIORDINA, "
        "RIEMPI, INVENTARIO, SALUTE, AIUTO, SAVE, LOAD [file], EXIT."
    )


def kw_is_not_tutto(testo: str) -> bool:
    t = (testo or "").lower()
    return "tutto" not in t and "ogni cosa" not in t


def _normalizza_azione(stato: Stato, a: str) -> str:
    a = (a or "").strip().lower()
    return stato.alias_azioni.get(a, a)


def _azioni_candidate(stato: Stato, a: str) -> List[str]:
    base = _normalizza_azione(stato, a)
    out = [base]
    for alt in stato.fallback_azioni.get(base, []):
        if alt not in out:
            out.append(alt)
    return out


def _sembra_input_azione(stato: Stato, raw_lower: str) -> bool:
    first = raw_lower.split(maxsplit=1)[0] if raw_lower else ""
    return first in stato.verbi_noti


def _normalizza_cmd(stato: Stato, cmd: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(cmd)
    out["a"] = _normalizza_azione(stato, str(out.get("a", "esamina")))
    for k in ("o", "su", "con", "dest", "in"):
        if isinstance(out.get(k), str):
            out[k] = out[k].strip()
    return out


def cmd_universale(stato: Stato, cmd: Dict[str, Any]) -> str:
    a = _normalizza_azione(stato, str(cmd.get("a", "esamina")))
    o_txt = str(cmd.get("o", "")).strip()
    su_txt = str(cmd.get("su") or cmd.get("con") or cmd.get("dest") or cmd.get("in") or "").strip()
    d = str(cmd.get("d", "")).upper()

    if a == "vai" and not d and o_txt:
        d = _DIREZIONI_RAPIDE.get(o_txt.lower(), o_txt.upper())

    # Comandi base
    if a == "vai":
        for u in stato.uscite_disponibili():
            if u.get("direzione") == d:
                stato.prima_visita.add(u["destinazione"])
                stato.stanza = u["destinazione"]
                stato.t_stanza[stato.stanza] = 0
                return descrivi_stanza(stato)

        for u in stato.ds.get("uscite", []):
            if u.get("direzione") == d and u.get("bloccata", False):
                return u.get("messaggio_blocco", "E bloccata.")
        return f"Non puoi andare a {d}."

    if a in ("inventario", "i"):
        if not stato.inv:
            return "Il tuo inventario e vuoto."
        nomi = [stato.oggetti[idx]["nome"] for idx in stato.inv if idx in stato.oggetti]
        return "Stai portando: " + " / ".join(nomi)

    if a in ("salute", "s"):
        barre = "#" * (stato.salute // 10)
        vuote = "." * (10 - stato.salute // 10)
        return f"Salute: {stato.salute}/{stato.salute_max} [{barre}{vuote}]"

    if a == "aiuto":
        return cmd_aiuto()

    if a == "fuggi":
        return "Non c'e motivo di scappare, oppure non puoi farlo in questa direzione."

    # Risoluzione entita
    visibili = stato.oggetti_visibili_stanza()
    id_obj = stato.trova_id_oggetto(o_txt, visibili + stato.inv)

    id_su_obj = stato.trova_id_oggetto(su_txt, visibili + stato.inv) if su_txt else None
    id_su: Optional[str] = id_su_obj or _virtual_tool_id(su_txt)

    # Frasi tipo "guarda sotto al tavolo": se il target finisce in dest/con/in,
    # usa quel target come oggetto primario per azioni esplorative.
    if not id_obj and id_su_obj and a in ("esamina", "cerca"):
        id_obj = id_su_obj

    # Caso speciale: comando con strumento "virtuale" come oggetto principale
    # es: inserisci braccio in foro -> o=braccio, in=foro
    if not id_obj and id_su_obj:
        virt = _virtual_tool_id(o_txt)
        if virt:
            obj_target = stato.oggetti[id_su_obj]
            res_virtuale = valuta_interazione(stato, obj_target.get("interazioni", []), a, virt)
            if res_virtuale:
                return res_virtuale

    # Interazioni stanza
    if not o_txt or o_txt.lower() == "stanza" or (not id_obj and a in ("esamina", "guarda", "cerca", "riordina")):
        res_stanza = valuta_interazione(stato, stato.ds.get("interazioni_stanza", []), a)
        if res_stanza:
            return res_stanza
        if a in ("esamina", "guarda", "osserva"):
            return descrivi_stanza(stato)
        return f"Non sai come fare '{a}' qui."

    if not id_obj and kw_is_not_tutto(o_txt):
        return f"Non vedi '{o_txt}' qui."

    # Sistema: prendi / lascia
    if a == "prendi":
        if o_txt.lower() == "tutto":
            presi: List[str] = []
            non_presi: List[str] = []
            for v_id in visibili:
                obj = stato.oggetti[v_id]
                if not obj.get("raccoglibile", False):
                    non_presi.append(obj["nome"])
                    continue
                if v_id not in stato.inv:
                    stato.inv.append(v_id)
                stato.oggetti_raccolti.add(v_id)
                _remove_from_all_revealed(stato, v_id)
                presi.append(obj["nome"])

            msg = ""
            if presi:
                msg += f"Hai raccolto: {', '.join(presi)}.\n"
            if non_presi:
                msg += f"Non puoi raccogliere: {', '.join(non_presi)}."
            return msg.strip() or "Non c'e niente da prendere."

        if not id_obj:
            return f"Non vedi '{o_txt}' qui."

        obj = stato.oggetti[id_obj]
        res_custom = valuta_interazione(stato, obj.get("interazioni", []), "prendi")
        if res_custom:
            return res_custom

        if not obj.get("raccoglibile", False):
            return f"Non puoi raccogliere {obj['nome']}."
        if id_obj in stato.inv:
            return "Lo hai gia preso."

        stato.inv.append(id_obj)
        stato.oggetti_raccolti.add(id_obj)
        _remove_from_all_revealed(stato, id_obj)
        return f"Raccogli {obj['nome']}."

    if a == "lascia":
        if not id_obj or id_obj not in stato.inv:
            return "Non hai questo oggetto."
        stato.inv.remove(id_obj)
        arr = stato.rivelati.setdefault(stato.stanza, [])
        if id_obj not in arr:
            arr.append(id_obj)
        return f"Lasci {stato.oggetti[id_obj]['nome']} sul pavimento."

    # Interazioni su oggetti
    if id_obj:
        obj1 = stato.oggetti[id_obj]
        azioni = _azioni_candidate(stato, a)

        for az in azioni:
            res = valuta_interazione(stato, obj1.get("interazioni", []), az, id_su)
            if res:
                return res

            if id_su_obj:
                obj2 = stato.oggetti[id_su_obj]
                res2 = valuta_interazione(stato, obj2.get("interazioni", []), az, id_obj)
                if res2:
                    return res2

        # Comodita: "accendi X" tenta automaticamente strumenti compatibili in inventario.
        if a in ("accendi", "usa") and not id_su_obj:
            for tool_id in list(stato.inv):
                tool_obj = stato.oggetti.get(tool_id)
                if not tool_obj:
                    continue
                for az in azioni:
                    res_tool = valuta_interazione(stato, tool_obj.get("interazioni", []), az, id_obj)
                    if res_tool:
                        return res_tool

        # Default elegante per esamina quando non ci sono interazioni dedicate.
        if a in ("esamina", "guarda", "osserva"):
            return obj1.get("descrizione", f"Osservi {obj1['nome']}.")

    return f"L'azione '{a}' non produce alcun effetto su questo."


# ===== Descrizione =====
def descrivi_stanza(stato: Stato, extra: str = "") -> str:
    ds = stato.ds
    nome = ds["nome"]
    atm = ds.get("atmosfera", "")

    for st_atm in ds.get("stati_atmosfera", []):
        cond = st_atm.get("condizione")
        if isinstance(cond, dict) and valuta_condizioni(stato, [cond]):
            atm += " " + st_atm.get("testo", "")

    uscite_nomi = [u["direzione"] for u in stato.uscite_disponibili()]
    oggetti = [stato.oggetti[o_id]["nome"] for o_id in stato.oggetti_visibili_stanza()]

    if USE_LLM:
        ctx = (
            f"Stanza: {nome}. Atmosfera: {atm}\n"
            f"Oggetti: {', '.join(oggetti) or 'nessuno'}.\n"
            f"Uscite libere: {', '.join(uscite_nomi) or 'nessuna'}.\n"
            f"LINGUA DI OUTPUT RICHIESTA: {stato.lingua.upper()}"
        )
        if extra:
            ctx += f"\nEvento in corso: {extra}."
        res = llm_descrivi(ctx)
        if res:
            return f"[{nome}]\n{res}"

    p = [f"[{nome}]", atm]
    if oggetti:
        p.append("Oggetti: " + ", ".join(oggetti))
    if uscite_nomi:
        p.append("Uscite: " + ", ".join(uscite_nomi))
    if extra:
        p.append(extra)
    return "\n".join([x for x in p if x])


# ===== Save/load =====
def salva_partita(stato: Stato, filename: str = "gamestatus.json") -> None:
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(stato.esporta_dati(), f, indent=4)
        print(f"\nSalvataggio completato in '{filename}'.")
    except Exception as e:
        print(f"\nErrore salvataggio: {e}")


def carica_partita(stato: Stato, filename: str = "gamestatus.json") -> bool:
    if not os.path.exists(filename):
        return False
    try:
        with open(filename, "r", encoding="utf-8") as f:
            stato.importa_dati(json.load(f))
        return True
    except Exception:
        return False


# ===== Main =====
def parse_cmd(stato: Stato, raw: str) -> List[Dict[str, Any]]:
    raw_lower = raw.lower().strip()

    if raw_lower in _DIREZIONI_RAPIDE:
        return [{"a": "vai", "d": _DIREZIONI_RAPIDE[raw_lower]}]

    parsed = llm_parse(stato, raw) if USE_LLM else None
    if parsed:
        normalizzati = [_normalizza_cmd(stato, c) for c in parsed if isinstance(c, dict)]
        if normalizzati:
            # Se l'LLM degrada a "esamina stanza" su un input chiaramente azione,
            # preferiamo il parser fallback deterministico.
            if (
                len(normalizzati) == 1
                and normalizzati[0].get("a") == "esamina"
                and str(normalizzati[0].get("o", "")).strip().lower() in ("", "stanza")
                and _sembra_input_azione(stato, raw_lower)
            ):
                return [_normalizza_cmd(stato, _fallback_parse(stato, raw))]
            return normalizzati

    return [_normalizza_cmd(stato, _fallback_parse(stato, raw))]


def main() -> None:
    hdr("UNIVERSAL TEXT ADVENTURE ENGINE v2")

    try:
        with open(DB_FILE, encoding="utf-8") as f:
            db = json.load(f)
    except FileNotFoundError:
        print(f"\nJSON Database '{DB_FILE}' non trovato.")
        sys.exit(1)

    stato = Stato(db)

    if USE_LLM:
        print(f"\nOllama Locale ({MODEL}) connesso.")
    else:
        print("\nModalita Fallback (no-LLM).")

    if os.path.exists("gamestatus.json"):
        carica_partita(stato, "gamestatus.json")
        stampa("[Caricamento Automatico] Partita ripresa!")
        print()
        stampa(descrivi_stanza(stato))
        sep()
    else:
        stampa("Ti risvegli nell'incubo...")
        print()
        stato.prima_visita.add(stato.stanza)
        stampa(descrivi_stanza(stato))
        sep()

    while True:
        print()
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not raw:
            continue

        raw_lower = raw.lower()

        if raw_lower == "save":
            salva_partita(stato)
            continue

        if raw_lower.startswith("load"):
            parti = raw.split(maxsplit=1)
            fname = parti[1].strip() if len(parti) > 1 else "gamestatus.json"
            if carica_partita(stato, fname):
                print("\n[Partita Caricata]\n")
                stampa(descrivi_stanza(stato))
            else:
                print(f"\n[Load fallito: '{fname}']")
            continue

        if raw_lower in ("exit", "quit", "q", "esci"):
            try:
                if input("Salvare? (s/n): ").strip().lower() in ("s", "si", "y", "yes"):
                    salva_partita(stato)
            except Exception:
                pass
            break

        if raw_lower.startswith("language ") or raw_lower.startswith("lingua "):
            stato.lingua = raw.split(" ", 1)[1]
            print(f"[Language: {stato.lingua.upper()}]")
            stampa(descrivi_stanza(stato))
            continue

        comandi = parse_cmd(stato, raw)

        for cmd in comandi:
            risposta = cmd_universale(stato, cmd)
            if risposta:
                print()
                stampa(risposta)

            if stato.morto() or stato.flags.get("Finale"):
                break

        if stato.morto():
            print()
            sep("=")
            stampa("GAME OVER.")
            sep("=")
            if os.path.exists("gamestatus.json"):
                os.remove("gamestatus.json")
            break

        if stato.flags.get("Finale"):
            print()
            sep("=")
            stampa("VITTORIA!")
            sep("=")
            if os.path.exists("gamestatus.json"):
                os.remove("gamestatus.json")
            break

        stato.turno += 1
        stato.t_stanza[stato.stanza] = stato.t_stanza.get(stato.stanza, 0) + 1

        msg_evento = processa_eventi(stato)
        if msg_evento:
            print()
            stampa(f"Evento: {msg_evento}")

        if stato.morto():
            print()
            sep("=")
            stampa("SEI MORTO.")
            sep("=")
            break


if __name__ == "__main__":
    main()
