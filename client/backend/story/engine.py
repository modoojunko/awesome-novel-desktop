"""Story deduction engine — round loop, checkpoint management, stage updates."""

import json
import time
import uuid

from ai_client import get_ai_client_for_novel
from filesystem.storage import get_storage
from prompts import load as load_prompt
from story.character_agent import run_all_decisions
from story.models import (
    CharacterState,
    Decision,
    RoundResult,
    SensoryInput,
    StageState,
)


class DeductionEngine:
    """Manages one deduction session."""

    def __init__(self, project_id: str, root_path: str):
        self.project_id = project_id
        self.root_path = root_path
        self.deduction_id = uuid.uuid4().hex[:12]
        self.stage = StageState()
        self.characters: dict[str, CharacterState] = {}
        self.history: list[RoundResult] = []
        self.seed: str = ""
        self.round = 0

    # ── Initialization ────────────────────────────────────────────

    async def load_from_project(self, chapter_ref: str | None = None):
        """Load stage and character data from project files."""
        # Load story premise and world setting
        story = await get_storage().read_yaml(self.root_path, "story.yaml") or {}
        self.stage.background = story.get("synopsis", "")
        world = (
            await get_storage().read_yaml(self.root_path, "settings/world-setting.yaml")
            or {}
        )

        # world-setting-v2：舞台段落（v1 旧形状在读边界归一化后取 stage）
        from settings.world_model import normalize_world

        self.stage.terrain = str(
            normalize_world(world).get("stage", "")
        ).strip()

        # Load chapter outline if specified（章族入库：DB 统一读入口）
        if chapter_ref:
            from workflow.engine import load_chapter

            chapter = await load_chapter(self.root_path, chapter_ref) or {}
            outline = chapter.get("outline", {})
            if isinstance(outline, dict):
                self.stage.terrain = self.stage.terrain or outline.get("location", "")

        # Load characters
        char_names = await get_storage().list_dir(
            self.root_path, "settings/character-setting"
        )
        for name in char_names:
            name_clean = name.replace(".yaml", "")
            data = (
                await get_storage().read_yaml(
                    self.root_path, f"settings/character-setting/{name_clean}.yaml"
                )
                or {}
            )
            char = CharacterState(
                character_id=name_clean,
                position="",
                stamina=100,
                emotion="平静",
                knowledge=[],
                cognition_6={
                    "world_view": data.get("world_view", ""),
                    "self_image": data.get("self_image", ""),
                    "values": data.get("values", ""),
                    "abilities": data.get("abilities", ""),
                    "skills": data.get("skills", ""),
                    "environment": data.get("environment", ""),
                },
                perception_config=data.get("perception", {}),
            )
            self.characters[name_clean] = char

    def _get_nested(self, d: dict, path: str, default: str = "") -> str:
        parts = path.split(".")
        for p in parts:
            if isinstance(d, dict):
                d = d.get(p, {})
            else:
                return default
        return str(d) if d else default

    # ── Seed ──────────────────────────────────────────────────────

    def set_seed(self, seed_text: str):
        """Set the trigger seed for this deduction."""
        self.seed = seed_text
        self.stage.events.append(
            {
                "round": 0,
                "actor": "系统",
                "action": "触发",
                "description": seed_text,
                "visibility": "公开",
            }
        )

    # ── Round execution ───────────────────────────────────────────

    async def run_round(self) -> RoundResult:
        """Execute one full round (Step 1 → Step 2 → Step 3)."""
        self.round += 1
        rn = self.round

        # Step 1: Build sensory inputs for each character
        sensory_inputs = self._build_sensory_inputs()

        # Step 2: Run character decisions in parallel
        decisions = await run_all_decisions(
            self.characters, sensory_inputs, self.stage, rn, self.project_id
        )

        # Step 3: Synthesize events and update state
        events = await self._synthesize_events(decisions)
        self._apply_events(events)

        # Build result
        result = RoundResult(
            round_number=rn,
            decisions=decisions,
            stage=self._clone_stage(),
            characters={k: self._clone_char(v) for k, v in self.characters.items()},
            events=events,
            checkpoint_id=f"cp-{rn}-{int(time.time())}",
        )
        self.history.append(result)
        return result

    def _build_sensory_inputs(self) -> dict[str, SensoryInput]:
        """Step 1: Build what each character perceives this round."""
        result = {}
        latest_events = [
            e for e in self.stage.events if e.get("round", 0) >= self.round - 1
        ]

        for cid, char in self.characters.items():
            see_parts = []
            hear_parts = []
            feel_parts = []

            # Environment
            if self.stage.terrain:
                see_parts.append(f"你身处{self.stage.terrain}")
            if self.stage.weather:
                feel_parts.append(f"天气{self.stage.weather}")
            if self.stage.lighting:
                see_parts.append(f"光线{self.stage.lighting}")

            # Events visible to this character
            for ev in latest_events:
                vis = ev.get("visibility", "公开")
                if vis == "公开" or vis == cid:
                    desc = ev.get("description", "")
                    hear_parts.append(desc)

            # Character's own position and condition
            if char.position:
                see_parts.append(f"你位于{char.position}")
            if char.stamina < 30:
                feel_parts.append("体力透支，急需休息")
            elif char.stamina < 60:
                feel_parts.append("有些疲惫")

            result[cid] = SensoryInput(
                see="；".join(see_parts) if see_parts else "（无特殊视觉）",
                hear="；".join(hear_parts) if hear_parts else "（周围安静）",
                smell="",
                feel="；".join(feel_parts) if feel_parts else "（状态正常）",
                environment=f"{self.stage.terrain} · {self.stage.time or '时间不明'}",
            )
        return result

    async def _synthesize_events(self, decisions: list[Decision]) -> list[dict]:
        """Step 3: Use LLM to synthesize character decisions into events."""
        if not decisions:
            return []

        decisions_text = []
        for d in decisions:
            action_desc = d.log.action_description or d.log.action_type
            decisions_text.append(f"  - {d.character_id}：{action_desc}")

        prompt = load_prompt("story_stage").format(
            stage=f"{self.stage.terrain} · 第{self.round}回合",
            decisions="\n".join(decisions_text),
        )

        try:
            client = await get_ai_client_for_novel(self.project_id)
            text = await client.chat(
                model="haiku",
                system="只输出 JSON 数组，不要其他文字。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                cleaned = cleaned.rsplit("```", 1)[0]
            events = json.loads(cleaned.strip())
            if isinstance(events, list):
                for ev in events:
                    ev["round"] = self.round
                return events
        except (ValueError, TypeError, KeyError):
            pass

        # Fallback: create basic events from decisions
        return [
            {
                "actor": d.character_id,
                "action": d.log.action_description or d.log.action_type,
                "target": d.log.action_target,
                "result": "",
                "visibility": "公开",
                "round": self.round,
            }
            for d in decisions
        ]

    def _apply_events(self, events: list[dict]):
        """Apply events to character state and stage."""
        for ev in events:
            # Add to public event pool
            if ev.get("visibility") in ("公开", None):
                self.stage.events.append(ev)

            # Update character knowledge based on events
            actor = ev.get("actor", "")
            if actor in self.characters:
                desc = ev.get("action", "")
                if desc and desc not in self.characters[actor].knowledge:
                    self.characters[actor].knowledge.append(desc)

    # ── Checkpoint management ─────────────────────────────────────

    def rewind_to(self, round_number: int) -> list[RoundResult]:
        """Rewind to a previous round checkpoint. Returns the remaining history."""
        if round_number < 0 or round_number >= len(self.history):
            raise ValueError(f"Invalid round number: {round_number}")

        self.round = round_number
        target = self.history[round_number]
        self.stage = self._clone_stage(target.stage)
        self.characters = {k: self._clone_char(v) for k, v in target.characters.items()}
        self.history = self.history[: round_number + 1]
        return self.history

    # ── Helpers ───────────────────────────────────────────────────

    def add_character(self, char: CharacterState):
        self.characters[char.character_id] = char

    def _clone_stage(self, stage: StageState | None = None) -> StageState:
        s = stage or self.stage
        return StageState(
            terrain=s.terrain,
            time=s.time,
            weather=s.weather,
            lighting=s.lighting,
            noise=s.noise,
            visibility_modifiers=s.visibility_modifiers,
            terrain_effects=s.terrain_effects,
            events=list(s.events),
            round=s.round,
        )

    def _clone_char(self, c: CharacterState) -> CharacterState:
        return CharacterState(
            character_id=c.character_id,
            position=c.position,
            stamina=c.stamina,
            emotion=c.emotion,
            urgency=c.urgency,
            knowledge=list(c.knowledge),
            relationships=dict(c.relationships),
            cognition_6=dict(c.cognition_6),
            perception_config=dict(c.perception_config),
        )

    def to_dict(self) -> dict:
        """Serialize engine state for API responses."""
        return {
            "deduction_id": self.deduction_id,
            "round": self.round,
            "stage": {
                "terrain": self.stage.terrain,
                "time": self.stage.time,
                "weather": self.stage.weather,
                "events": self.stage.events[-20:],  # Last 20 events
            },
            "characters": {
                cid: {
                    "id": cid,
                    "position": c.position,
                    "stamina": c.stamina,
                    "emotion": c.emotion,
                    "urgency": c.urgency,
                    "knowledge": c.knowledge,
                }
                for cid, c in self.characters.items()
            },
            "seed": self.seed,
        }
