#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generatore automatico di database avventure data-driven con supporto Ollama.

Ispirato allo schema di `database_mondo_data_driven_v2.json` e pensato per essere
compatibile con `GE_Avventura_data_driven_v3.py`.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
TEMPLATE_DB = Path(__file__).with_name("database_mondo_data_driven_v2.json")


@dataclass
class AdventureRequest:
    tema: str
    atmosfera: str
    numero_stanze: int
    preferenze: List[str]


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, url: str = DEFAULT_OLLAMA_URL, enabled: bool = True) -> None:
        self.model = model
        self.url = url
        self.enabled = enabled

    def chat(self, system: str, user: str, json_format: bool = False, temperature: float = 0.6, max_tokens: int = 700) -> Optional[str]:
        if not self.enabled:
            return None

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_format:
            payload["format"] = "json"

        try:
            from urllib import request as urlrequest
            req = urlrequest.Request(
                self.url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8")
            parsed = json.loads(body)
            return parsed.get("message", {}).get("content", "").strip()
        except Exception:
            return None


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return cleaned[:40] or "elemento"


def _parse_json(raw: Optional[str]) -> Optional[Any]:
    if not raw:
        return None
    candidate = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    candidate = re.sub(r"\s*```$", "", candidate)
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _load_template_config() -> Dict[str, Any]:
    data = json.loads(TEMPLATE_DB.read_text(encoding="utf-8"))
    return data.get("configurazione", {})


def collect_preferences(ollama: OllamaClient, tema: str, atmosfera: str, numero_stanze: int) -> List[str]:
    system = (
        "Sei un game designer. Genera al massimo 3 domande di chiarimento per personalizzare "
        "una nuova avventura testuale. Restituisci JSON: {\"questions\":[\"...\"]}."
    )
    user = (
        f"Tema: {tema}\nAtmosfera: {atmosfera}\nNumero stanze: {numero_stanze}\n"
        "Le domande devono essere brevi e mirate (stile, difficoltà, puzzle, tono)."
    )

    parsed = _parse_json(ollama.chat(system, user, json_format=True, temperature=0.3, max_tokens=180)) or {}
    questions = [q.strip() for q in parsed.get("questions", []) if isinstance(q, str) and q.strip()][:3]

    if not questions:
        questions = [
            "Vuoi un'avventura più narrativa o più puzzle?",
            "Quale livello di difficoltà preferisci (facile/medio/difficile)?",
            "Ci sono elementi che vuoi assolutamente includere o evitare?",
        ]

    print("\n--- Personalizzazione avventura ---")
    answers: List[str] = []
    for question in questions:
        answer = input(f"{question}\n> ").strip()
        if answer:
            answers.append(f"{question} {answer}")
    return answers


def build_rooms_with_llm(ollama: OllamaClient, req: AdventureRequest) -> Optional[Dict[str, Any]]:
    system = (
        "Sei un worldbuilder per avventure testuali. Restituisci SOLO JSON valido con questa forma: "
        "{\"titolo\":str,\"obiettivo\":str,\"rooms\":[{\"id\":str,\"nome\":str,\"atmosfera\":str,"
        "\"oggetti\":[{\"id\":str,\"nome\":str,\"raccoglibile\":bool}],\"hint\":str}]}"
    )
    user = (
        f"Genera {req.numero_stanze} stanze coerenti.\n"
        f"Tema: {req.tema}\nAtmosfera globale: {req.atmosfera}\n"
        f"Preferenze utente: {' | '.join(req.preferenze) if req.preferenze else 'nessuna'}\n"
        "Regole: id in snake_case, almeno 1 oggetto per stanza, niente spoiler sul finale."
    )
    parsed = _parse_json(ollama.chat(system, user, json_format=True, temperature=0.8, max_tokens=1200))
    if not isinstance(parsed, dict):
        return None
    rooms = parsed.get("rooms")
    if not isinstance(rooms, list) or len(rooms) < req.numero_stanze:
        return None
    return parsed


def build_fallback_rooms(req: AdventureRequest) -> Dict[str, Any]:
    rooms: List[Dict[str, Any]] = []
    for i in range(req.numero_stanze):
        idx = i + 1
        room_name = f"Luogo {idx} del {req.tema.title()}"
        rooms.append(
            {
                "id": f"stanza_{idx}",
                "nome": room_name,
                "atmosfera": f"{req.atmosfera}. In questa area senti dettagli unici del tema {req.tema}.",
                "oggetti": [
                    {
                        "id": f"oggetto_{idx}",
                        "nome": f"Reperto {idx}",
                        "raccoglibile": True,
                    }
                ],
                "hint": "Osserva gli oggetti e prova a usarli nelle stanze successive.",
            }
        )

    return {
        "titolo": f"Cronache di {req.tema.title()}",
        "obiettivo": "Raggiungi l'ultima stanza e scopri il segreto finale.",
        "rooms": rooms,
    }


def normalize_rooms(raw_rooms: List[Dict[str, Any]], numero_stanze: int) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for i, room in enumerate(raw_rooms[:numero_stanze]):
        room_name = str(room.get("nome") or f"Stanza {i+1}")
        room_id = _slugify(str(room.get("id") or room_name))
        atmos = str(room.get("atmosfera") or "Un luogo carico di mistero.")

        objects: List[Dict[str, Any]] = []
        for j, obj in enumerate(room.get("oggetti", [])):
            obj_name = str(obj.get("nome") or f"Oggetto {i+1}_{j+1}")
            obj_id = _slugify(str(obj.get("id") or obj_name or f"obj_{i+1}_{j+1}"))
            objects.append(
                {
                    "id": obj_id,
                    "nome": obj_name,
                    "raccoglibile": bool(obj.get("raccoglibile", True)),
                    "interazioni": [],
                }
            )

        if not objects:
            objects.append(
                {
                    "id": f"oggetto_{i+1}",
                    "nome": f"Indizio {i+1}",
                    "raccoglibile": True,
                    "interazioni": [],
                }
            )

        normalized.append(
            {
                "id": room_id or f"stanza_{i+1}",
                "nome": room_name,
                "atmosfera": atmos,
                "hint": str(room.get("hint") or "Esamina ciò che ti circonda."),
                "objects": objects,
            }
        )
    return normalized


def compose_database(template_cfg: Dict[str, Any], generated: Dict[str, Any], numero_stanze: int) -> Dict[str, Any]:
    rooms = normalize_rooms(generated["rooms"], numero_stanze)

    stanze: List[Dict[str, Any]] = []
    oggetti_map: Dict[str, Dict[str, Any]] = {}

    for idx, room in enumerate(rooms):
        exits: List[Dict[str, str]] = []
        if idx > 0:
            exits.append({"direzione": "SUD", "destinazione": rooms[idx - 1]["id"]})
        if idx < len(rooms) - 1:
            exits.append({"direzione": "NORD", "destinazione": rooms[idx + 1]["id"]})

        visible_obj_ids = []
        for obj in room["objects"]:
            obj_id = obj["id"]
            suffix = 2
            while obj_id in oggetti_map:
                obj_id = f"{obj['id']}_{suffix}"
                suffix += 1
            obj["id"] = obj_id
            oggetti_map[obj_id] = {
                "id": obj_id,
                "nome": obj["nome"],
                "raccoglibile": obj["raccoglibile"],
                "interazioni": obj["interazioni"],
            }
            visible_obj_ids.append(obj_id)

        stanze.append(
            {
                "id": room["id"],
                "nome": room["nome"],
                "atmosfera": room["atmosfera"],
                "uscite": exits,
                "oggetti_visibili": visible_obj_ids,
                "oggetti_nascosti": [],
                "eventi": [],
                "interazioni_stanza": [],
            }
        )

    configurazione = dict(template_cfg)
    configurazione["stanza_iniziale"] = stanze[0]["id"]
    configurazione.setdefault("salute_max", 100)
    configurazione.setdefault("variabili_iniziali", {})
    configurazione.setdefault("alias_azioni", {})
    configurazione.setdefault("fallback_azioni", {})

    return {
        "meta": {
            "titolo": generated.get("titolo", "Nuova Avventura"),
            "obiettivo": generated.get("obiettivo", "Esplora il mondo e sopravvivi."),
            "creato_il": datetime.now().isoformat(timespec="seconds"),
        },
        "configurazione": configurazione,
        "stanze": stanze,
        "oggetti": list(oggetti_map.values()),
    }


def build_walkthrough(db: Dict[str, Any]) -> List[Dict[str, str]]:
    by_id = {room["id"]: room for room in db["stanze"]}
    current = db["configurazione"]["stanza_iniziale"]

    steps: List[Dict[str, str]] = [
        {
            "comando": "salute",
            "atteso": "Il motore mostra la salute iniziale.",
        }
    ]

    visited = set()
    while current not in visited:
        visited.add(current)
        room = by_id[current]
        steps.append({"comando": "esamina", "atteso": f"Compare la descrizione della stanza '{room['nome']}'."})

        for obj_id in room.get("oggetti_visibili", [])[:1]:
            obj_name = next((o["nome"] for o in db["oggetti"] if o["id"] == obj_id), obj_id)
            steps.append({"comando": f"prendi {obj_name}", "atteso": f"L'oggetto '{obj_name}' entra in inventario (se raccoglibile)."})

        north = next((u for u in room.get("uscite", []) if u.get("direzione") == "NORD"), None)
        if not north:
            break
        steps.append({"comando": "vai nord", "atteso": "Il personaggio raggiunge la stanza successiva."})
        current = north["destinazione"]

    steps.append({"comando": "inventario", "atteso": "L'inventario elenca gli oggetti raccolti durante il percorso."})
    return steps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera database JSON + walkthrough per nuove avventure.")
    parser.add_argument("--tema", help="Tema dell'avventura")
    parser.add_argument("--atmosfera", help="Atmosfera generale")
    parser.add_argument("--stanze", type=int, help="Numero di stanze")
    parser.add_argument("--output-dir", default="output_avventure", help="Directory di output")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modello Ollama")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Endpoint Ollama chat API")
    parser.add_argument("--no-llm", action="store_true", help="Disattiva LLM e usa fallback deterministico")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    tema = args.tema or input("Tema della nuova avventura: ").strip()
    atmosfera = args.atmosfera or input("Atmosfera desiderata: ").strip()
    numero_stanze = args.stanze or int(input("Numero di stanze: ").strip())

    if numero_stanze < 2:
        raise SystemExit("Il numero minimo di stanze è 2.")

    ollama = OllamaClient(model=args.model, url=args.ollama_url, enabled=not args.no_llm)
    preferenze = collect_preferences(ollama, tema, atmosfera, numero_stanze)
    req = AdventureRequest(tema=tema, atmosfera=atmosfera, numero_stanze=numero_stanze, preferenze=preferenze)

    generated = build_rooms_with_llm(ollama, req) or build_fallback_rooms(req)
    db = compose_database(_load_template_config(), generated, numero_stanze)
    walkthrough = build_walkthrough(db)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = _slugify(tema) or "avventura"
    db_path = out_dir / f"{base_name}_{stamp}.json"
    walkthrough_path = out_dir / f"{base_name}_{stamp}_walkthrough_test.json"

    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    walkthrough_payload = {
        "titolo": db.get("meta", {}).get("titolo", "Walkthrough"),
        "db_file": db_path.name,
        "steps": walkthrough,
    }
    walkthrough_path.write_text(json.dumps(walkthrough_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nGenerazione completata ✅")
    print(f"Database avventura: {db_path}")
    print(f"Walkthrough di test: {walkthrough_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
