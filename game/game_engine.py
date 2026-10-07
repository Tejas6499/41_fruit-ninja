import pygame
import random
from .fruit import Fruit

WHITE = (255, 255, 255)
BOMB_BLACK = (30, 30, 30)
FRUIT_COLORS = [(220, 60, 60), (230, 140, 40), (230, 200, 40), (90, 180, 90)]

WINDOW_LEAVE = getattr(pygame, "WINDOWLEAVE", None)

class GameEngine:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.fruits = []
        self.trail = []
        self._last_pos = None

        self.spawn_interval = 55
        self._spawn_timer = 0
        self.bomb_chance = 0.15
        self.speed_scale = 1.0

        self.lives = 3
        self.score = 0
        self.font = pygame.font.SysFont("Arial", 28)
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
            self._last_pos = None
            self.trail.clear()

    def _handle_motion(self, pos):
        x, y = pos
        prev_x, prev_y = self._last_pos if self._last_pos is not None else pos

        for fruit in self.fruits:
            if not fruit.sliced and fruit.intersects_segment(prev_x, prev_y, x, y):
                self._slice(fruit)

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

        if self.game_over and not getattr(self, "_game_over_logged", False):
            print("Game over! Final score:", self.score)
            self._game_over_logged = True
