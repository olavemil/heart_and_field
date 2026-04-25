# Field & Heart — Technical Addendum v0.2
## Post-PoC Systems: Background Animation · Quirks & Secrets · Event Structure

Supplements Technical Setup Document v0.1. Assumes the PoC game loop, phase simulation, basic event selection, narrative templates, and Ren'Py shell are running.

> **Convention:** All enum values are canonical identifiers. Use verbatim in blueprints, chain tables, and LLM prompts. No free strings where an enum is defined.

---

## 1. Background Animation

Four independent layers compose the final background. Each responds to game state separately without regenerating images.

| Layer | Description |
|---|---|
| 1 — Variant set | 2–3 generated images of the same scene, crossfading on a 60–90 s timer |
| 2 — Noise overlay | Scrolling texture at low alpha, scene- and weather-conditional |
| 3 — Colour grade | Tint + brightness pass, driven by time-of-day and weather |
| 4 — Mood grade | Secondary tint driven by momentum/morale/tension, stacks on layer 3 |

### 1.1 Variant Set

```python
@dataclass
class BackgroundSet:
    scene_type:     SceneType
    scene_instance: SceneInstance
    context_hash:   str
    images:         list[str]       # 2-3 paths, same scene, slight variation
    current_index:  int = 0

    def next_variant(self) -> str:
        self.current_index = (self.current_index + 1) % len(self.images)
        return self.images[self.current_index]

VARIATION_SUFFIXES = [
    "",
    ", slightly different light angle",
    ", subtle atmospheric variation",
]

def generate_background_set(
    scene_type: SceneType,
    scene_instance: SceneInstance,
    context: BackgroundContext,
) -> BackgroundSet:
    base_prompt = BACKGROUND_PROMPTS[scene_type].format(**context.to_dict())
    images = []
    for i, suffix in enumerate(VARIATION_SUFFIXES):
        seed = BACKGROUND_SEED_BASE + hash(scene_instance) + i
        path = sd_generate_cached(base_prompt + suffix, seed, scene_type, i)
        images.append(path)
    return BackgroundSet(scene_type, scene_instance, hash(context), images)
```

### 1.2 Noise Overlays

```python
class NoiseOverlay(Enum):
    FILM_GRAIN   = "grain"      # always present, very low alpha
    LIGHT_DUST   = "dust"       # indoor scenes
    HEAT_SHIMMER = "shimmer"    # outdoor midday
    RAIN_STREAK  = "rain"       # weather-driven
    CROWD_BLUR   = "crowd"      # stadium only

class OverlayAnim(Enum):
    SCROLL_RANDOM = "scroll_random"
    SCROLL_UP     = "scroll_up"
    SCROLL_DOWN   = "scroll_down"
    PULSE         = "pulse"
    STATIC        = "static"

@dataclass
class OverlaySpec:
    path:      str
    alpha:     float
    animation: OverlayAnim
    speed:     float

OVERLAY_SPECS: dict[NoiseOverlay, OverlaySpec] = {
    NoiseOverlay.FILM_GRAIN:   OverlaySpec("overlays/grain.png",   0.06, SCROLL_RANDOM, 0.5),
    NoiseOverlay.LIGHT_DUST:   OverlaySpec("overlays/dust.png",    0.12, SCROLL_UP,     0.3),
    NoiseOverlay.HEAT_SHIMMER: OverlaySpec("overlays/shimmer.png", 0.10, PULSE,         0.2),
    NoiseOverlay.RAIN_STREAK:  OverlaySpec("overlays/rain.png",    0.20, SCROLL_DOWN,   0.8),
    NoiseOverlay.CROWD_BLUR:   OverlaySpec("overlays/crowd.png",   0.15, SCROLL_RANDOM, 0.4),
}

SCENE_OVERLAYS: dict[SceneType, list[NoiseOverlay]] = {
    SceneType.LOCKER_ROOM:     [FILM_GRAIN, LIGHT_DUST],
    SceneType.PITCH:           [FILM_GRAIN, CROWD_BLUR],
    SceneType.TRAINING_GROUND: [FILM_GRAIN],
    SceneType.BAR:             [FILM_GRAIN, LIGHT_DUST],
    SceneType.POOL:            [FILM_GRAIN, HEAT_SHIMMER],
    # weather-conditional overlays added at runtime
}
```

### 1.3 Colour Grading

```python
@dataclass
class ColorGrade:
    tint:       str     # hex
    alpha:      float
    brightness: float   # 1.0 = neutral
    saturation: float   # 1.0 = neutral

class TimeOfDay(Enum):
    DAWN      = "dawn"
    MORNING   = "morning"
    MIDDAY    = "midday"
    AFTERNOON = "afternoon"
    EVENING   = "evening"
    NIGHT     = "night"

class Weather(Enum):
    CLEAR    = "clear"
    OVERCAST = "overcast"
    RAIN     = "rain"

class SceneMood(Enum):
    NEUTRAL   = "neutral"
    TENSE     = "tense"
    EUPHORIC  = "euphoric"
    MELANCHOLY = "melancholy"
    CHARGED   = "charged"

TIME_OF_DAY_GRADES: dict[TimeOfDay, ColorGrade] = {
    TimeOfDay.DAWN:      ColorGrade("FF8C42", 0.12, 0.85, 0.90),
    TimeOfDay.MORNING:   ColorGrade("FFF4E0", 0.06, 1.00, 1.00),
    TimeOfDay.MIDDAY:    ColorGrade("FFFFFF", 0.00, 1.05, 1.05),
    TimeOfDay.AFTERNOON: ColorGrade("FFD580", 0.10, 0.95, 0.95),
    TimeOfDay.EVENING:   ColorGrade("FF6B35", 0.18, 0.80, 0.85),
    TimeOfDay.NIGHT:     ColorGrade("1A1A3E", 0.30, 0.60, 0.70),
}

WEATHER_GRADES: dict[Weather, ColorGrade] = {
    Weather.CLEAR:    ColorGrade("FFFACD", 0.08, 1.10, 1.10),
    Weather.OVERCAST: ColorGrade("8899AA", 0.15, 0.85, 0.80),
    Weather.RAIN:     ColorGrade("445566", 0.20, 0.75, 0.70),
}

MOOD_GRADES: dict[SceneMood, ColorGrade] = {
    SceneMood.NEUTRAL:    ColorGrade("FFFFFF", 0.00, 1.00, 1.00),
    SceneMood.TENSE:      ColorGrade("330000", 0.08, 1.00, 0.90),
    SceneMood.EUPHORIC:   ColorGrade("FFFFAA", 0.10, 1.05, 1.15),
    SceneMood.MELANCHOLY: ColorGrade("334466", 0.12, 0.90, 0.75),
    SceneMood.CHARGED:    ColorGrade("FF4400", 0.06, 1.00, 1.10),
}
```

Grades are stacked multiplicatively: time-of-day × weather × mood. Generate grade tint images as solid-color PNGs at session start from the hex values. Swap image references on condition change with a short linear alpha transition (4–8 s).

### 1.4 Ren'Py ATL

```renpy
image bg_live:
    $ bg = engine.get_background_set(scene_type)
    expression bg.images[0]
    block:
        linear 2.0  alpha 1.0
        pause  58.0
        linear 3.0  alpha 0.0
        $ _ = bg.next_variant()
        expression bg.images[bg.current_index]
        linear 3.0  alpha 1.0
        repeat

# subpixel True prevents mechanical pixel-snap on grain scroll
image overlay_grain:
    "overlays/grain.png"
    subpixel True
    block:
        linear 0.4  xoffset 2  yoffset 1
        linear 0.3  xoffset -1 yoffset 2
        linear 0.4  xoffset 1  yoffset -1
        repeat

image scene_live:
    fixed:
        "bg_live"
        "overlay_grain"  alpha 0.06
        "overlay_dust"   alpha 0.12    # conditional: indoor
        "grade_time"     alpha 0.15    # solid-color PNG, swapped on ToD change
        "grade_mood"     alpha 0.08    # solid-color PNG, swapped on mood change
```

---

## 2. Quirks

Quirks are two-dimensional: a **domain** (which area of life) and a **pattern** (the behavioural shape). Stat modifiers, relationship chemistry, and event weight bias all derive from the combination via lookup tables — no per-quirk authoring needed.

### 2.1 Dimensions

```python
class QuirkDomain(Enum):
    PERFORMANCE = "performance"   # training, match execution
    SOCIAL      = "social"        # relationships, group dynamics
    EMOTIONAL   = "emotional"     # stress response, mood regulation
    COGNITIVE   = "cognitive"     # decision-making, pattern recognition
    PHYSICAL    = "physical"      # body, appearance, health habits

class QuirkPattern(Enum):
    COMPULSIVE   = "compulsive"   # repeats behaviour beyond usefulness
    AVOIDANT     = "avoidant"     # systematically sidesteps something
    SEEKING      = "seeking"      # actively pursues something
    REACTIVE     = "reactive"     # strong response to specific triggers
    RIGID        = "rigid"        # resistant to change in this domain
    PERFORMATIVE = "performative" # behaves differently when observed

@dataclass
class Quirk:
    domain:  QuirkDomain
    pattern: QuirkPattern

    # All derived from (domain, pattern) lookup — not stored per quirk
    # stat_modifiers, relationship_affinities, relationship_frictions,
    # event_weight_rules, visibility, reveal_condition
```

Example mappings:

| Quirk label | Domain | Pattern |
|---|---|---|
| Superstitious | COGNITIVE | COMPULSIVE |
| Showboat | PERFORMANCE | PERFORMATIVE |
| Conflict-avoidant | SOCIAL | AVOIDANT |
| Crumbles under scrutiny | EMOTIONAL | REACTIVE |
| Gym obsessive | PHYSICAL | SEEKING |
| Tactically rigid | COGNITIVE | RIGID |

### 2.2 Visibility

```python
class QuirkVisibility(Enum):
    VISIBLE   = "visible"    # apparent immediately
    INFERABLE = "inferable"  # emerges under mild pressure
    HIDDEN    = "hidden"     # only surfaces under specific conditions

@dataclass
class QuirkReveal:
    quirk:             Quirk
    visibility:        QuirkVisibility
    reveal_event_tags: list[str]         # tags that expose a hidden quirk
    reveal_familiarity: float | None     # relationship threshold alternative
```

### 2.3 Affinity & Friction

```python
# Affinity: domain-pattern pairs that work well together
QUIRK_AFFINITIES: dict[tuple, list[tuple]] = {
    (PERFORMANCE, SEEKING):    [(PERFORMANCE, COMPULSIVE), (SOCIAL, SEEKING)],
    (SOCIAL, SEEKING):         [(EMOTIONAL, REACTIVE), (SOCIAL, PERFORMATIVE)],
    (COGNITIVE, RIGID):        [(PERFORMANCE, COMPULSIVE)],
}

# Friction: pairs that generate conflict events
QUIRK_FRICTIONS: dict[tuple, list[tuple]] = {
    (COGNITIVE, RIGID):        [(COGNITIVE, AVOIDANT), (SOCIAL, SEEKING)],
    (PERFORMANCE, PERFORMATIVE): [(PERFORMANCE, AVOIDANT)],
    (EMOTIONAL, REACTIVE):     [(SOCIAL, RIGID)],
}
```

Affinity/friction between characters' quirk pairs biases event weight — conflict events weight up when friction pairs share a scene, warm events weight up for affinity pairs. No scripting required.

---

## 3. Secrets

Secrets are narrative keys composed from typed aspects. They gate arcs, connect characters across the social graph, and expose gradually through play.

### 3.1 Secret Membership

```python
class SecretRole(Enum):
    OWNER       = "owner"       # holds the secret, most to lose
    PARTICIPANT = "participant" # involved, may not know the full shape
    WITNESS     = "witness"     # knows, not involved — most dangerous
    SUSPECT     = "suspect"     # doesn't know, but others think they might

@dataclass
class SecretMembership:
    character_id:        str
    role:                SecretRole
    exposure:            float          # how much of the secret this member knows [0-1]
    knows_other_members: list[str]      # character ids known to also be in the secret
```

### 3.2 Secret Structure

```python
class SecretCategory(Enum):
    AGENDA     = "agenda"
    TABOO      = "taboo"
    CONNECTION = "connection"
    HISTORY    = "history"
    IDENTITY   = "identity"

@dataclass
class Secret:
    id:               str
    category:         SecretCategory
    aspects:          list[SecretAspect]
    memberships:      list[SecretMembership]
    related_secrets:  list[SecretRelation]

    unlocks_arcs:     list[str]
    blocks_arcs:      list[str]
    unlocks_events:   list[EventId]

    exposure_level:   float = 0.0
    reveal_triggers:  list[str] = field(default_factory=list)  # event tags
    reveal_threshold: float = 0.8

    # Generated fields — populated by initialise_secret()
    mechanical:       str = ""
    description:      str = ""
    aspect_phrases:   dict[str, AspectPhrases] = field(default_factory=dict)

    # Hard cap: secrets cannot reference other secrets recursively beyond one layer
    meta_secret:      MetaSecret | None = None
```

### 3.3 Secret Aspects — Full Enum Taxonomy

All aspect fields are enumerated. No free strings except generated descriptions.

```python
class AspectType(Enum):
    RELATIONSHIP = "relationship"
    AGENDA       = "agenda"
    TABOO        = "taboo"
    HISTORY      = "history"
    IDENTITY     = "identity"

# RELATIONSHIP aspects
class RelationType(Enum):
    PARENT          = "parent"
    CHILD           = "child"
    SIBLING         = "sibling"
    FORMER_LOVER    = "former_lover"
    CURRENT_LOVER   = "current_lover"
    MENTOR          = "mentor"
    PROTEGE         = "protege"
    CREDITOR        = "creditor"
    DEBTOR          = "debtor"
    FORMER_TEAMMATE = "former_teammate"
    EMPLOYER        = "employer"
    RIVAL           = "rival"

@dataclass
class RelationshipAspect(SecretAspect):
    type:     AspectType = AspectType.RELATIONSHIP
    relation: RelationType = None
    target:   str | None = None          # character id or placeholder id
    mutual:   bool = False               # does the target know?

# AGENDA aspects
class AgendaGoal(Enum):
    PROTECT_CHARACTER   = "protect_character"
    SECURE_TRANSFER     = "secure_transfer"
    EXPOSE_CHARACTER    = "expose_character"
    PRESERVE_POSITION   = "preserve_position"
    GAIN_LEVERAGE       = "gain_leverage"
    SEEK_RECONCILIATION = "seek_reconciliation"
    SABOTAGE_CHARACTER  = "sabotage_character"
    EXTRACT_INFORMATION = "extract_information"

class AgendaMethod(Enum):
    INGRATIATING = "ingratiating"
    OBSERVING    = "observing"
    MANIPULATING = "manipulating"
    CONFIDING    = "confiding"
    ISOLATING    = "isolating"
    PERFORMING   = "performing"

@dataclass
class AgendaAspect(SecretAspect):
    type:   AspectType = AspectType.AGENDA
    goal:   AgendaGoal = None
    method: AgendaMethod = None
    target: str | None = None           # character id being pursued

# TABOO aspects
class TabooSubject(Enum):
    FAMILY_CONNECTION   = "family_connection"
    PAST_INCIDENT       = "past_incident"
    FORMER_CLUB         = "former_club"
    HEALTH_CONDITION    = "health_condition"
    FINANCIAL_SITUATION = "financial_situation"
    IDENTITY_FACT       = "identity_fact"
    RELATIONSHIP        = "relationship"

class TabooOrigin(Enum):
    CONTRACTUAL  = "contractual"
    SHAME        = "shame"
    PROTECTION   = "protection"
    TRAUMA       = "trauma"
    LEGAL        = "legal"
    PROFESSIONAL = "professional"

@dataclass
class TabooAspect(SecretAspect):
    type:         AspectType = AspectType.TABOO
    subject:      TabooSubject = None
    origin:       TabooOrigin = None
    trigger_tags: list[str] = field(default_factory=list)

# HISTORY aspects
class HistoryEventType(Enum):
    PREVIOUS_CLUB  = "previous_club"
    ROMANTIC       = "romantic"
    INCIDENT       = "incident"
    SHARED_LOSS    = "shared_loss"
    BETRAYAL       = "betrayal"
    COLLABORATION  = "collaboration"
    RIVALRY        = "rivalry"

@dataclass
class HistoryAspect(SecretAspect):
    type:        AspectType = AspectType.HISTORY
    event_type:  HistoryEventType = None
    shared_with: list[str] = field(default_factory=list)  # character ids
    known_to:    list[str] = field(default_factory=list)  # who already knows
```

### 3.4 Cross-Character Relations

```python
class SecretRelationType(Enum):
    SHARED    = "shared"      # both hold the same secret
    OPPOSING  = "opposing"    # their secrets conflict
    DEPENDENT = "dependent"   # this secret only matters because of theirs
    AWARE_OF  = "aware_of"    # this character knows the other's secret

@dataclass
class SecretRelation:
    other_character_id: str
    other_secret_id:    str
    relation_type:      SecretRelationType
```

`AWARE_OF` creates a meta-secret one level deep: Character A's secret is that they know Character B's secret. This is represented as a `MetaSecret` with its own memberships and aspect phrases, but no further nesting.

```python
@dataclass
class MetaSecret:
    id:              str
    base_secret_id:  str
    aspects:         list[SecretAspect]
    memberships:     list[SecretMembership]
    is_meta:         bool = True        # cannot spawn further meta-secrets
    # same generated fields as Secret
    mechanical:      str = ""
    description:     str = ""
    aspect_phrases:  dict[str, AspectPhrases] = field(default_factory=dict)
```

### 3.5 Exposure-Banded Narration

Aspect phrases are generated at four exposure levels. The LLM call happens once at character initialisation and is cached.

```python
class ExposureBand(Enum):
    HIDDEN    = "hidden"     # 0.0–0.2  almost nothing visible
    GLIMPSED  = "glimpsed"   # 0.2–0.5  something is off
    SUSPECTED = "suspected"  # 0.5–0.8  shape is clear, details uncertain
    KNOWN     = "known"      # 0.8–1.0  substantially understood

@dataclass
class AspectPhrases:
    aspect_id: str
    hidden:    str
    glimpsed:  str
    suspected: str
    known:     str

    def by_band(self, band: ExposureBand) -> str:
        return getattr(self, band.value)
```

Generation prompt (single call, JSON response):

```python
def generate_aspect_phrases(
    aspect: SecretAspect,
    mechanical: str,
    secret_description: str,
) -> AspectPhrases:
    prompt = f"""Mechanical fact (do not contradict): {mechanical}
Secret description: {secret_description}
Aspect: {aspect.id}

Write four narrator phrases for this aspect at increasing revelation levels.
hidden:    vague sense only, 8-12 words, do not name the secret
glimpsed:  something feels off, no specifics, 8-12 words
suspected: shape is clear, details uncertain, 8-15 words
known:     substantially understood, 8-15 words

Respond as JSON: {{"hidden": "...", "glimpsed": "...", "suspected": "...", "known": "..."}}
Do not invent facts absent from the mechanical description."""
    return AspectPhrases(aspect_id=aspect.id, **parse_json_safely(llm_call(prompt)))
```

### 3.6 LLM Pipeline

Four short, bounded calls at initialisation. Nothing regenerated during play.

```
aspects (structured)
    ↓  compose_mechanical_description()   ← deterministic, no LLM
mechanical sentence
    ↓  flavor_secret()                    ← LLM call 1
secret description
    ↓  generate_aspect_phrases()          ← LLM call 2 (one per aspect)
aspect phrase bands
    ↓  [optional] reformulate_secret()   ← LLM call 3, consistency pass
final description
```

```python
def compose_mechanical_description(secret: Secret, cast: dict) -> str:
    TEMPLATES = {
        AspectType.RELATIONSHIP: "{holder} is the {relation} of {target}",
        AspectType.AGENDA:       "{holder} is {method} in order to {goal}",
        AspectType.TABOO:        "{holder} will not discuss {subject} due to {origin}",
        AspectType.HISTORY:      "{holder} and {shared_with} share a {event_type} history",
        AspectType.IDENTITY:     "{holder} is concealing {identity_fact}",
    }
    parts = [
        TEMPLATES[a.type].format(**resolve_aspect_fields(a, cast))
        for a in secret.aspects
    ]
    return ". ".join(parts) + "."

def initialise_secret(secret: Secret, cast: dict, character: Character) -> Secret:
    secret.mechanical   = compose_mechanical_description(secret, cast)
    secret.description  = flavor_secret(secret.mechanical, character)
    secret.aspect_phrases = {
        a.id: generate_aspect_phrases(a, secret.mechanical, secret.description)
        for a in secret.aspects
    }
    if needs_consistency_pass(secret):
        secret.description = reformulate_secret(
            secret.description, secret.aspect_phrases, secret.mechanical
        )
    return secret
```

### 3.7 Placeholder Characters

When an aspect references a character who doesn't yet exist:

```python
@dataclass
class CharacterPlaceholder:
    id:                       str            # stable — used immediately in aspects
    required_role:            CharacterRole
    required_relation:        RelationType
    scheduling_priority:      float
    introduction_event_types: list[EventId]  # which events can introduce them
    secret_ids:               list[str]      # secrets referencing this placeholder

def resolve_placeholder(p: CharacterPlaceholder, world: WorldState) -> TierBCharacter:
    char = generate_character(role=p.required_role, id=p.id)
    for sid in p.secret_ids:
        world.secrets[sid].bind_placeholder(p.id, char.id)
    return char
```

The placeholder id is stable from the moment the secret is composed. When the real character is created, `bind_placeholder` marks the placeholder resolved — all existing references continue to work.

### 3.8 Secret Visibility in Events

Event access checks membership role and exposure against the observing character:

```python
def secret_visible_to(
    secret: Secret | MetaSecret,
    observer_id: str,
    aspect_id: str,
) -> tuple[bool, str | None]:
    membership = secret.membership_for(observer_id)
    if not membership:
        # non-member: only visible if widely suspected
        if secret.exposure_level > 0.7:
            return True, secret.aspect_phrases[aspect_id].suspected
        return False, None
    band = exposure_band(membership.exposure)
    if band == ExposureBand.HIDDEN:
        return False, None
    return True, secret.aspect_phrases[aspect_id].by_band(band)
```

Events requiring secret involvement:

```python
@dataclass
class EventBlueprint:
    ...
    requires_aspects:     list[AspectType]   # at least one participant must have these
    boosted_by_aspects:   list[AspectType]   # weight bonus if present
    requires_secret_role: SecretRole | None  # e.g. WITNESS gates blackmail events
    reveals_exposure:     float              # how much this event advances exposure
```

---

## 4. Event Structure

### 4.1 Scene Taxonomy

```python
class SceneCategory(Enum):
    SPORT         = "sport"
    SOCIAL        = "social"
    PRIVATE       = "private"
    TRANSIT       = "transit"
    MEDIA         = "media"
    INSTITUTIONAL = "institutional"

class SceneType(Enum):
    # SPORT
    PITCH           = "pitch"
    TRAINING_GROUND = "training_ground"
    GYM             = "gym"
    LOCKER_ROOM     = "locker_room"
    STANDS          = "stands"
    TUNNEL          = "tunnel"
    MEDICAL         = "medical"
    # SOCIAL
    RESTAURANT      = "restaurant"
    BAR             = "bar"
    CAFE            = "cafe"
    CLUB            = "club"
    PARK            = "park"
    POOL            = "pool"
    BEACH           = "beach"
    PARTY_VENUE     = "party_venue"
    # PRIVATE
    APARTMENT       = "apartment"
    HOUSE           = "house"
    MANSION         = "mansion"
    COMPOUND        = "compound"
    HOTEL_ROOM      = "hotel_room"
    # TRANSIT
    BUS             = "bus"
    PLANE           = "plane"
    CAR             = "car"
    STATION         = "station"
    AIRPORT         = "airport"
    # MEDIA
    PRESS_ROOM      = "press_room"
    STUDIO          = "studio"
    PHOTO_SHOOT     = "photo_shoot"
    # INSTITUTIONAL
    OFFICE          = "office"
    BOARDROOM       = "boardroom"
    HOSPITAL        = "hospital"
    COURTROOM       = "courtroom"

class SceneInstance(Enum):
    # Pattern: TYPE_MODIFIER
    APARTMENT_SHARED  = "apartment_shared"
    APARTMENT_SOLO    = "apartment_solo"
    APARTMENT_UPSCALE = "apartment_upscale"
    HOUSE_FAMILY      = "house_family"
    HOUSE_RENTED      = "house_rented"
    MANSION_OWN       = "mansion_own"
    MANSION_EVENT     = "mansion_event"
    BAR_LOCAL         = "bar_local"
    BAR_UPSCALE       = "bar_upscale"
    RESTAURANT_CASUAL = "restaurant_casual"
    RESTAURANT_FORMAL = "restaurant_formal"
    HOTEL_AWAY        = "hotel_away"
    HOTEL_LAYOVER     = "hotel_layover"
    # etc.
```

### 4.2 Scene Graph

Adjacency drives geographic event chaining — a scene set in a bar can continue in an adjacent scene without feeling arbitrary.

```python
SCENE_ADJACENCY: dict[SceneType, list[SceneType]] = {
    SceneType.LOCKER_ROOM:     [SceneType.TUNNEL,   SceneType.MEDICAL,  SceneType.GYM],
    SceneType.TUNNEL:          [SceneType.PITCH,    SceneType.STANDS,   SceneType.LOCKER_ROOM],
    SceneType.GYM:             [SceneType.LOCKER_ROOM, SceneType.MEDICAL],
    SceneType.TRAINING_GROUND: [SceneType.GYM,      SceneType.LOCKER_ROOM],
    SceneType.BAR:             [SceneType.RESTAURANT, SceneType.CLUB,   SceneType.HOTEL_ROOM],
    SceneType.RESTAURANT:      [SceneType.BAR,      SceneType.CAFE],
    SceneType.HOTEL_ROOM:      [SceneType.BAR,      SceneType.POOL,     SceneType.AIRPORT],
    SceneType.POOL:            [SceneType.HOTEL_ROOM, SceneType.BAR],
    SceneType.AIRPORT:         [SceneType.PLANE,    SceneType.STATION],
    SceneType.PLANE:           [SceneType.AIRPORT],
    SceneType.BUS:             [SceneType.TRAINING_GROUND, SceneType.STADIUM],
}
```

### 4.3 Event Dimensions

Events have three dimensions. An event id is the combination of all three.

```python
class EventNature(Enum):
    CONFRONTATION = "confrontation"
    ADMISSION     = "admission"
    REVELATION    = "revelation"
    NEGOTIATION   = "negotiation"
    CELEBRATION   = "celebration"
    CONSOLATION   = "consolation"
    OBSERVATION   = "observation"   # watching/noticing without acting
    INVITATION    = "invitation"
    REJECTION     = "rejection"
    COLLABORATION = "collaboration"
    COMPETITION   = "competition"
    ISOLATION     = "isolation"     # character alone, self-directed

class EventDomain(Enum):
    SPORT         = "sport"
    RELATIONSHIP  = "relationship"
    INSTITUTIONAL = "institutional"
    PERSONAL      = "personal"
    SECRET        = "secret"        # requires secret membership

class EventTone(Enum):
    HOSTILE    = "hostile"
    TENSE      = "tense"
    NEUTRAL    = "neutral"
    WARM       = "warm"
    ROMANTIC   = "romantic"
    PLAYFUL    = "playful"
    MELANCHOLY = "melancholy"
    TRIUMPHANT = "triumphant"

@dataclass
class EventId:
    nature: EventNature
    domain: EventDomain
    tone:   EventTone

    def key(self) -> str:
        return f"{self.domain.value}_{self.nature.value}_{self.tone.value}"
```

### 4.4 Event List

Full enumeration of valid combinations. Not all combinations are meaningful — only those listed here have blueprints.

**SPORT domain**

| Nature | Tone | Description |
|---|---|---|
| CONFRONTATION | HOSTILE | Blame after loss |
| CONFRONTATION | TENSE | Tactical disagreement |
| COLLABORATION | NEUTRAL | Training drill |
| COLLABORATION | WARM | Breakthrough session |
| OBSERVATION | NEUTRAL | Scouting a rival |
| CELEBRATION | TRIUMPHANT | Post-win |
| CONSOLATION | MELANCHOLY | Post-loss |
| REVELATION | TENSE | Injury discovered |
| NEGOTIATION | TENSE | Contract pressure |
| COMPETITION | HOSTILE | Direct rival clash |
| ISOLATION | MELANCHOLY | Player alone, struggling |

**RELATIONSHIP domain**

| Nature | Tone | Description |
|---|---|---|
| CONFRONTATION | HOSTILE | Open conflict |
| CONFRONTATION | TENSE | Suppressed tension |
| ADMISSION | MELANCHOLY | Vulnerability, private struggle |
| ADMISSION | ROMANTIC | Confession |
| REVELATION | TENSE | Unwanted discovery |
| REVELATION | HOSTILE | Forced exposure |
| INVITATION | WARM | Social inclusion |
| INVITATION | ROMANTIC | Romantic advance |
| REJECTION | HOSTILE | Active dismissal |
| REJECTION | MELANCHOLY | Gentle refusal |
| CELEBRATION | WARM | Shared joy |
| CELEBRATION | PLAYFUL | Lighthearted bonding |
| CONSOLATION | WARM | Support offered |
| CONSOLATION | MELANCHOLY | Shared grief |
| OBSERVATION | NEUTRAL | Noticing something about someone |
| COMPETITION | TENSE | Social rivalry |
| COLLABORATION | WARM | Working together outside sport |
| ISOLATION | MELANCHOLY | Withdrawal after rejection |

**INSTITUTIONAL domain**

| Nature | Tone | Description |
|---|---|---|
| NEGOTIATION | TENSE | Contract discussion |
| NEGOTIATION | HOSTILE | Ultimatum |
| REVELATION | TENSE | Club news, transfer rumour |
| CONFRONTATION | HOSTILE | Management clash |
| CELEBRATION | TRIUMPHANT | Award, public recognition |
| OBSERVATION | NEUTRAL | Media attention |
| ISOLATION | TENSE | Dropped from squad |

**PERSONAL domain**

| Nature | Tone | Description |
|---|---|---|
| ADMISSION | MELANCHOLY | Private struggle |
| REVELATION | TENSE | Family news |
| ISOLATION | MELANCHOLY | Homesickness, disconnection |
| CONSOLATION | WARM | Support from unexpected source |
| CELEBRATION | WARM | Personal milestone |

**SECRET domain** — require secret membership to trigger

| Nature | Tone | Description |
|---|---|---|
| OBSERVATION | NEUTRAL | A knowing look |
| CONFRONTATION | TENSE | Leverage applied |
| CONFRONTATION | HOSTILE | Blackmail |
| ADMISSION | MELANCHOLY | Partial reveal, vulnerability |
| ADMISSION | ROMANTIC | Trust-based reveal |
| REVELATION | HOSTILE | Forced exposure |
| REVELATION | TENSE | Accidental exposure |
| NEGOTIATION | TENSE | Protective deal |
| ISOLATION | MELANCHOLY | Alone with the weight of knowing |

### 4.5 Event Chaining

Events chain along a shared dimension. Three chain types:

```python
class ChainDimension(Enum):
    SCENE    = "scene"      # same location, tone or nature shifts
    NATURE   = "nature"     # same action type, domain or tone shifts
    DOMAIN   = "domain"     # same thematic space, nature shifts
    ADJACENT = "adjacent"   # scene graph adjacency, anything shifts

@dataclass
class EventChainEdge:
    from_id:   EventId
    to_id:     EventId
    dimension: ChainDimension
    condition: str | None = None    # optional state gate
```

Representative chain table:

| From | To | Dimension | Condition |
|---|---|---|---|
| REL · CONFRONTATION · HOSTILE | REL · ADMISSION · MELANCHOLY | SCENE | — |
| REL · CONFRONTATION · HOSTILE | REL · ADMISSION · ROMANTIC | SCENE | attraction > 0.5 |
| REL · CONFRONTATION · TENSE | REL · NEGOTIATION · TENSE | SCENE | — |
| SPORT · CONFRONTATION · HOSTILE | REL · CONFRONTATION · HOSTILE | NATURE | — |
| REL · ADMISSION · MELANCHOLY | PERS · ADMISSION · MELANCHOLY | NATURE | — |
| REL · OBSERVATION · NEUTRAL | SEC · OBSERVATION · NEUTRAL | SCENE | observer_has_meta_secret |
| REL · CONFRONTATION · HOSTILE | SEC · CONFRONTATION · TENSE | SCENE | participant_has_secret |
| SPORT · CELEBRATION · TRIUMPHANT | REL · CELEBRATION · PLAYFUL | ADJACENT | — |
| REL · REJECTION · MELANCHOLY | REL · ISOLATION · MELANCHOLY | ADJACENT | — |

The thematic pivot you noted — `CONFRONTATION + POOL + HOSTILE → ADMISSION + POOL + ROMANTIC` — is a SCENE chain with a tone and nature shift but persistent location. The scene context carries the meaning of the shift.

### 4.6 Updated EventBlueprint

```python
@dataclass
class EventBlueprint:
    id:                   EventId
    tags:                 set[str]
    participants:         list[RoleSlot]
    blocks:               list[SceneBlock]

    # Graph edges
    prerequisites:        list[str]
    unlocks:              list[str]
    disables:             list[str]
    chain_edges:          list[EventChainEdge]

    # Weighting
    weight_modifiers:     list[WeightRule]
    boosted_by_quirks:    list[tuple[QuirkDomain, QuirkPattern]]
    penalised_by_quirks:  list[tuple[QuirkDomain, QuirkPattern]]

    # Secret gating
    requires_aspects:     list[AspectType]
    boosted_by_aspects:   list[AspectType]
    requires_secret_role: SecretRole | None
    reveals_exposure:     float

    # Narrative
    outcome_summaries:    dict[str, str]    # branch_id -> authored mechanical summary
    carries_arc_context:  bool = False

    # Scene
    valid_scene_types:    list[SceneType]
    preferred_instances:  list[SceneInstance]
```

---

## 5. Development Sequence (Updated)

Appended to the sequence in v0.1:

| Phase | Deliverable |
|---|---|
| 11 — Background animation | BackgroundSet generation, OverlaySpec lookup, ColorGrade pipeline, ATL scene composite |
| 12 — Quirk system | QuirkDomain/Pattern enums, lookup tables for stat modifiers and affinities, visibility mechanic |
| 13 — Secret aspects | All aspect enums, SecretMembership, ExposureBand, AspectPhrases dataclass |
| 14 — Secret LLM pipeline | compose_mechanical_description(), flavor_secret(), generate_aspect_phrases(), reformulate_secret() |
| 15 — Placeholder characters | CharacterPlaceholder, resolve_placeholder(), introduction event scheduling |
| 16 — Scene taxonomy | SceneType/Instance enums, SCENE_ADJACENCY graph, BackgroundContext per type |
| 17 — Event dimensions | EventNature/Domain/Tone enums, EventId, full blueprint list, chain edge table |
| 18 — Content pass | Author blueprints for each valid event combination, chain edges, quirk/secret content |

---

*End of Technical Addendum v0.2*
