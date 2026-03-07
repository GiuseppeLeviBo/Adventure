#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Motore avventura testuale data-driven.

Obiettivo:
- Nessuna regola di gioco hard-coded legata a uno scenario specifico.
- Tutta la logica narrativa/interattiva risiede nel database JSON.
- Lo stato del motore contiene solo campi universali (es. lingua, flag, variabili, inventario).

Uso:
    python Avventura_data_driven.py --db database_mondo_generic.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_COMMANDS: Dict[str, str] = {
    "n": "go NORD",
    "s": "go SUD",
    "e": "go EST",
    "o": "go OVEST",
    "i": "inventory",
    "guarda": "look",
}


@dataclass
class GameState:
    room: str
    language: str = "it"
    health: int = 100
    turn: int = 1
    inventory: List[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    vars: Dict[str, Any] = field(default_factory=dict)
    game_over: bool = False

    def has_item(self, item_id: str) -> bool:
        return item_id in self.inventory

    def has_flag(self, flag: str) -> bool:
        return flag in self.flags


class DataDrivenEngine:
    def __init__(self, world: Dict[str, Any]):
        self.world = world
        defaults = world.get("state_defaults", {})
        self.rooms: Dict[str, Dict[str, Any]] = world["rooms"]

        self.state = GameState(
            room=world["start_room"],
            language=defaults.get("language", "it"),
            health=defaults.get("health", 100),
            inventory=list(defaults.get("inventory", [])),
            flags=set(defaults.get("flags", [])),
            vars=dict(defaults.get("vars", {})),
        )

        self.messages = world.get("messages", {})
        self.commands = {**DEFAULT_COMMANDS, **world.get("command_aliases", {})}

    # ---------- rendering ----------
    def room(self) -> Dict[str, Any]:
        return self.rooms[self.state.room]

    def visible_objects(self, room_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rid = room_id or self.state.room
        out = []
        for obj in self.rooms[rid].get("objects", []):
            if self.eval_condition(obj.get("visible_if", "True")):
                out.append(obj)
        return out

    def available_exits(self) -> List[Dict[str, Any]]:
        out = []
        for ex in self.room().get("exits", []):
            if self.eval_condition(ex.get("condition", "True")):
                out.append(ex)
        return out

    def describe_room(self) -> str:
        r = self.room()
        parts = [f"[{r.get('name', self.state.room)}]", r.get("description", "")]

        objs = self.visible_objects()
        if objs:
            parts.append("Oggetti: " + ", ".join(o["name"] for o in objs))

        exits = self.available_exits()
        if exits:
            ex_t = " | ".join(f"{x['direction']} -> {self.rooms[x['to']].get('name', x['to'])}" for x in exits)
            parts.append("Uscite: " + ex_t)

        return "\n".join(p for p in parts if p)

    # ---------- mini-rule language ----------
    def _ctx(self) -> Dict[str, Any]:
        return {
            "room": self.state.room,
            "health": self.state.health,
            "turn": self.state.turn,
            "inventory": self.state.inventory,
            "flags": self.state.flags,
            "vars": self.state.vars,
        }

    def eval_condition(self, expr: Any) -> bool:
        if expr is None:
            return True
        if isinstance(expr, bool):
            return expr
        if not isinstance(expr, str):
            return bool(expr)

        ctx = self._ctx()
        safe_globals = {"__builtins__": {}}
        try:
            return bool(eval(expr, safe_globals, ctx))
        except Exception:
            return False

    def render_template(self, text: str) -> str:
        if not text:
            return ""
        ctx = self._ctx()
        try:
            return text.format(**ctx)
        except Exception:
            return text

    def apply_effects(self, effects: List[Dict[str, Any]]) -> List[str]:
        out: List[str] = []
        for effect in effects:
            et = effect.get("type")
            if et == "message":
                out.append(self.render_template(effect.get("text", "")))
            elif et == "set_flag":
                self.state.flags.add(effect["name"])
            elif et == "clear_flag":
                self.state.flags.discard(effect["name"])
            elif et == "set_var":
                self.state.vars[effect["name"]] = effect.get("value")
            elif et == "inc_var":
                k = effect["name"]
                self.state.vars[k] = int(self.state.vars.get(k, 0)) + int(effect.get("value", 1))
            elif et == "add_item":
                item = effect["item"]
                if item not in self.state.inventory:
                    self.state.inventory.append(item)
            elif et == "remove_item":
                item = effect["item"]
                if item in self.state.inventory:
                    self.state.inventory.remove(item)
            elif et == "move_player":
                self.state.room = effect["to"]
            elif et == "damage":
                self.state.health -= int(effect.get("value", 0))
            elif et == "heal":
                self.state.health += int(effect.get("value", 0))
            elif et == "end_game":
                self.state.game_over = True
                out.append(self.render_template(effect.get("text", "Game over.")))
        return out

    def run_events(self, trigger: str, payload: Optional[Dict[str, Any]] = None) -> List[str]:
        payload = payload or {}
        events = []
        events.extend(self.world.get("global_events", []))
        events.extend(self.room().get("events", []))

        out: List[str] = []
        for ev in events:
            if ev.get("trigger") != trigger:
                continue
            if not self.eval_condition(ev.get("condition", "True")):
                continue
            if payload:
                wanted = ev.get("match", {})
                if any(payload.get(k) != v for k, v in wanted.items()):
                    continue
            out.extend(self.apply_effects(ev.get("effects", [])))
        return out

    # ---------- command handling ----------
    def normalize(self, raw: str) -> str:
        return self.commands.get(raw.strip().lower(), raw.strip())

    def find_object(self, token: str) -> Optional[Dict[str, Any]]:
        token = token.strip().lower()
        for obj in self.visible_objects():
            if obj["id"].lower() == token or obj["name"].lower() == token:
                return obj
        return None

    def execute(self, raw: str) -> List[str]:
        cmd = self.normalize(raw)
        parts = cmd.split()
        if not parts:
            return []

        action = parts[0].lower()
        out: List[str] = []

        if action in {"look", "l", "esamina"}:
            if len(parts) == 1:
                out.append(self.describe_room())
            else:
                token = " ".join(parts[1:])
                obj = self.find_object(token)
                if obj:
                    out.append(obj.get("description", obj["name"]))
                    out.extend(self.apply_effects(obj.get("on_examine", [])))
                else:
                    out.append(self.messages.get("object_not_found", "Non vedi nulla del genere."))

        elif action in {"go", "vai"} and len(parts) > 1:
            direction = parts[1].upper()
            ex = next((e for e in self.available_exits() if e["direction"].upper() == direction), None)
            if ex:
                self.state.room = ex["to"]
                out.extend(self.apply_effects(ex.get("on_use", [])))
                out.append(self.describe_room())
                out.extend(self.run_events("on_enter"))
            else:
                out.append(self.messages.get("blocked_exit", "Non puoi andare da quella parte."))

        elif action in {"take", "prendi"} and len(parts) > 1:
            token = " ".join(parts[1:])
            obj = self.find_object(token)
            if not obj:
                out.append(self.messages.get("object_not_found", "Non vedi nulla del genere."))
            elif not obj.get("takeable", False):
                out.append(self.messages.get("not_takeable", "Non puoi raccoglierlo."))
            elif obj["id"] in self.state.inventory:
                out.append(self.messages.get("already_have", "Ce l'hai già."))
            else:
                self.state.inventory.append(obj["id"])
                out.append(self.render_template(obj.get("take_text", f"Hai preso {obj['name']}.")))
                out.extend(self.apply_effects(obj.get("on_take", [])))
                out.extend(self.run_events("on_take", {"object": obj["id"]}))

        elif action in {"drop", "lascia"} and len(parts) > 1:
            token = " ".join(parts[1:]).lower()
            found = next((i for i in self.state.inventory if i.lower() == token), None)
            if not found:
                out.append(self.messages.get("not_in_inventory", "Non è nel tuo inventario."))
            else:
                self.state.inventory.remove(found)
                out.append(self.messages.get("drop_ok", "Lasciato."))

        elif action in {"inventory", "inventario"}:
            out.append("Inventario: " + (", ".join(self.state.inventory) if self.state.inventory else "vuoto"))

        elif action in {"help", "aiuto"}:
            out.append(self.messages.get("help", "Comandi: look, go <dir>, take <obj>, drop <obj>, inventory, quit"))

        elif action in {"quit", "esci"}:
            self.state.game_over = True
            out.append(self.messages.get("bye", "Alla prossima."))

        else:
            out.append(self.messages.get("unknown", "Comando non riconosciuto."))

        out.extend(self.run_events("on_command", {"action": action, "raw": raw}))

        self.state.turn += 1
        out.extend(self.run_events("on_turn"))

        if self.state.health <= 0:
            self.state.game_over = True
            out.append(self.messages.get("death", "Sei morto."))

        return [m for m in out if m]


def load_world(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Il database deve essere un oggetto JSON con chiavi top-level (rooms, start_room, ...).")
    if "rooms" not in data or "start_room" not in data:
        raise ValueError("Database invalido: servono almeno 'rooms' e 'start_room'.")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Motore avventura testuale data-driven")
    parser.add_argument("--db", default="database_mondo_generic.json", help="Path del database mondo")
    args = parser.parse_args()

    world = load_world(Path(args.db))
    engine = DataDrivenEngine(world)

    print(engine.describe_room())
    for line in engine.run_events("on_enter"):
        print(line)

    while not engine.state.game_over:
        raw = input("\n> ").strip()
        for line in engine.execute(raw):
            print(line)


if __name__ == "__main__":
    main()
