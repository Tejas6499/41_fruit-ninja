import array
import math
import pygame
import random
from .fruit import Fruit

# Game Engine

WHITE = (255, 255, 255)
BOMB_BLACK = (30, 30, 30)
FRUIT_COLORS = [(220, 60, 60), (230, 140, 40), (230, 200, 40), (90, 180, 90)]
OVERLAY_COLOR = (0, 0, 0, 170)  # RGBA: black at ~2/3 opacity, dims the playfield

STARTING_LIVES = 3

# spawn_interval: frames between spawns (higher = fewer fruit on screen)
# bomb_chance:    probability that a spawn is a bomb
# speed_scale:    multiplier on launch speed
DIFFICULTIES = {
    "easy":   {"spawn_interval": 80, "bomb_chance": 0.08, "speed_scale": 0.9},
    "medium": {"spawn_interval": 55, "bomb_chance": 0.15, "speed_scale": 1.0},
    "hard":   {"spawn_interval": 35, "bomb_chance": 0.25, "speed_scale": 1.2},
}

# Keys offered on the game-over screen.
DIFFICULTY_KEYS = {
    pygame.K_e: "easy",
    pygame.K_m: "medium",
    pygame.K_h: "hard",
}
QUIT_KEY = pygame.K_q
MENU_TEXT = "E - Easy   M - Medium   H - Hard   Q - Quit"

# Fired when the pointer leaves the window (pygame 2.0.1+). None on older
# versions, in which case it simply never matches an event type.
WINDOW_LEAVE = getattr(pygame, "WINDOWLEAVE", None)


# --- Sound effects ----------------------------------------------------------
# Generated in code, so the repo needs no audio files and no extra dependency
# (the array module is part of Python's standard library). Each builder
# returns one channel of samples as floats in the range -1.0 .. 1.0.

def _slice_samples(rate):
    """Short rising 'swish': a tone sweeping 700 -> 1700 Hz in 0.09 s."""
    count = int(rate * 0.09)
    samples = []
    phase = 0.0
    for i in range(count):
        progress = i / count
        frequency = 700 + 1000 * progress
        phase += 2 * math.pi * frequency / rate
        fade_out = (1 - progress) ** 2
        samples.append(fade_out * math.sin(phase))
    return _normalise(samples, 0.45)


def _bomb_samples(rate):
    """Low 'boom': muffled noise plus a 55 Hz thump, dying away over 0.45 s."""
    count = int(rate * 0.45)
    rng = random.Random(0)  # own generator, so the game's random stream is untouched
    smoothing = 1 - math.exp(-2 * math.pi * 400 / rate)  # low-pass at ~400 Hz
    samples = []
    rumble = 0.0
    for i in range(count):
        t = i / rate
        rumble += smoothing * (rng.uniform(-1, 1) - rumble)
        thump = math.sin(2 * math.pi * 55 * t)
        fade_out = math.exp(-8 * t) * (1 - i / count)
        samples.append(fade_out * (4 * rumble + 0.6 * thump))
    return _normalise(samples, 0.7)


def _game_over_samples(rate):
    """Three falling notes (G4, E4, C4), the last one held longer."""
    samples = []
    for frequency, seconds in ((392.00, 0.18), (329.63, 0.18), (261.63, 0.40)):
        count = int(rate * seconds)
        for i in range(count):
            t = i / rate
            fade_in = min(1.0, i / (rate * 0.01))  # 10 ms, avoids a click
            fade_out = 1 - i / count
            tone = (math.sin(2 * math.pi * frequency * t)
                    + 0.3 * math.sin(2 * math.pi * 2 * frequency * t))
            samples.append(fade_in * fade_out * tone)
    return _normalise(samples, 0.4)


def _normalise(samples, peak):
    """Scale samples so the loudest one sits at `peak` (0.0 .. 1.0)."""
    loudest = max(abs(s) for s in samples) or 1.0
    return [s * peak / loudest for s in samples]


SOUND_BUILDERS = {
    "slice": _slice_samples,
    "bomb": _bomb_samples,
    "game_over": _game_over_samples,
}


def _build_sounds():
    """Return {name: pygame.mixer.Sound}, or {} if audio isn't available.

    An empty dict means "sound disabled": the game carries on silently.
    """
    try:
        # main.py's pygame.init() normally starts the mixer already; if it
        # couldn't (or wasn't asked to), try once here.
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        rate, sample_format, channels = pygame.mixer.get_init()

        # The packing below writes signed 16-bit samples (pygame's default).
        if sample_format != -16:
            return {}

        sounds = {}
        for name, builder in SOUND_BUILDERS.items():
            pcm = array.array("h")
            for sample in builder(rate):
                value = int(sample * 32767)
                # Same signal on every output channel (mono, stereo, ...).
                pcm.extend([value] * channels)
            sounds[name] = pygame.mixer.Sound(buffer=pcm)
        return sounds
    except (pygame.error, NotImplementedError):
        # pygame.error: no audio device / mixer failed to start.
        # NotImplementedError: this pygame build has no mixer module.
        return {}


class GameEngine:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        # Things that last for the whole session (built once).
        self.font = pygame.font.SysFont("Arial", 28)
        self.title_font = pygame.font.SysFont("Arial", 72, bold=True)
        self.final_score_font = pygame.font.SysFont("Arial", 36)
        self.menu_font = pygame.font.SysFont("Arial", 24)

        # Semi-transparent sheet drawn over the playfield on game over.
        self._overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self._overlay.fill(OVERLAY_COLOR)

        # Sound effects. Empty if there is no usable audio device, in which
        # case _play() quietly does nothing.
        self._sounds = _build_sounds()
        self.sound_enabled = bool(self._sounds)

        # Everything that belongs to a single game is set up in start_game(),
        # so the first game and every replay go through the same code.
        self.start_game("medium")

    def start_game(self, difficulty):
        """Reset all per-game state and begin a new game on `difficulty`."""
        settings = DIFFICULTIES[difficulty]
        self.spawn_interval = settings["spawn_interval"]
        self.bomb_chance = settings["bomb_chance"]
        self.speed_scale = settings["speed_scale"]

        self.fruits = []
        self.trail = []  # recent mouse positions, drawn as the "blade"
        self._last_pos = None  # previous mouse position; None = no stroke yet
        self._spawn_timer = 0

        self.lives = STARTING_LIVES
        self.score = 0
        self.game_over = False

    def spawn_fruit(self):
        x = random.randint(60, self.width - 60)
        vy = -random.uniform(13, 16) * self.speed_scale
        vx = random.uniform(-2, 2)
        gravity = 0.35
        kind = "bomb" if random.random() < self.bomb_chance else "fruit"

        fruit = Fruit(x, self.height + 30, vx, vy, gravity, kind=kind)
        fruit.color = BOMB_BLACK if kind == "bomb" else random.choice(FRUIT_COLORS)
        self.fruits.append(fruit)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._handle_motion(event.pos)
        elif event.type == WINDOW_LEAVE:
            # The pointer left the window. Start a fresh stroke when it
            # comes back, otherwise the exit and re-entry points would be
            # joined into one long blade that slices everything between
            # them (bombs included).
            self._last_pos = None
            self.trail.clear()
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event.key)

    def _handle_key(self, key):
        # The menu only exists on the game-over screen; during a game
        # these keys do nothing.
        if not self.game_over:
            return

        if key in DIFFICULTY_KEYS:
            self.start_game(DIFFICULTY_KEYS[key])
        elif key == QUIT_KEY:
            # Ask for the same shutdown as clicking the window's close
            # button: main.py's loop sees QUIT, stops, and calls
            # pygame.quit().
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _handle_motion(self, pos):
        x, y = pos
        # Test the whole path the blade travelled since the last event, not
        # just where it ended up. On the first event of a stroke there is no
        # previous point, so the segment collapses to the current position.
        prev_x, prev_y = self._last_pos if self._last_pos is not None else pos

        # Once the game is over the blade is cosmetic: nothing gets sliced,
        # so score and lives are frozen at their final values.
        if not self.game_over:
            for fruit in self.fruits:
                if not fruit.sliced and fruit.intersects_segment(prev_x, prev_y, x, y):
                    self._slice(fruit)
                    if self.game_over:
                        # That was a bomb - don't score anything else
                        # this same swipe happens to cross.
                        break

        # Still tracked after game over so the trail keeps drawing.
        self._last_pos = pos

        self.trail.append(pos)
        if len(self.trail) > 15:
            self.trail.pop(0)

    def _slice(self, fruit):
        fruit.sliced = True
        if fruit.kind == "bomb":
            self._play("bomb")
            self._end_game()
        else:
            self.score += 1
            self._play("slice")

    def _end_game(self):
        # The only place game_over is switched on, so the game-over sound
        # plays exactly once per game however the game ended.
        if self.game_over:
            return
        self.game_over = True
        self._play("game_over")

    def _play(self, name):
        sound = self._sounds.get(name)
        if sound is not None:
            sound.play()

    def handle_input(self):
        # Reserved for continuously-held-key input; this game is
        # entirely mouse-driven, so there's nothing to poll here.
        pass

    def update(self):
        if self.game_over:
            return

        self._spawn_timer += 1
        if self._spawn_timer >= self.spawn_interval:
            self._spawn_timer = 0
            self.spawn_fruit()

        still_alive = []
        for fruit in self.fruits:
            fruit.update()
            if fruit.sliced:
                continue
            if fruit.off_screen(self.height):
                if fruit.kind == "fruit":
                    self.lives -= 1
                continue
            still_alive.append(fruit)
        self.fruits = still_alive

        if self.lives <= 0:
            self._end_game()

    def render(self, screen):
        for fruit in self.fruits:
            color = getattr(fruit, "color", WHITE)
            pygame.draw.circle(screen, color, (int(fruit.x), int(fruit.y)), fruit.radius)

        if len(self.trail) >= 2:
            pygame.draw.lines(screen, WHITE, False, self.trail, 3)

        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        screen.blit(score_text, (10, 10))
        lives_text = self.font.render(f"Lives: {self.lives}", True, WHITE)
        screen.blit(lives_text, (self.width - 130, 10))

        if self.game_over:
            self._render_game_over(screen)

    def _render_game_over(self, screen):
        # Drawn last, so it dims everything rendered above (fruit, trail, HUD).
        screen.blit(self._overlay, (0, 0))

        center_x = self.width // 2
        center_y = self.height // 2

        title = self.title_font.render("GAME OVER", True, WHITE)
        screen.blit(title, title.get_rect(center=(center_x, center_y - 60)))

        final_score = self.final_score_font.render(f"Final Score: {self.score}", True, WHITE)
        screen.blit(final_score, final_score.get_rect(center=(center_x, center_y + 20)))

        menu = self.menu_font.render(MENU_TEXT, True, WHITE)
        screen.blit(menu, menu.get_rect(center=(center_x, center_y + 85)))
