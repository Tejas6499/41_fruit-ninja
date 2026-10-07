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
            self.game_over = True
        else:
            self.score += 1

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
            self.game_over = True

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
