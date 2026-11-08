"""Generate and visibly solve a black-on-white maze."""

import random
import time

from apps.base_app import BaseApp
from lib.epd import display, display_height, display_width


PADDING = 10
CELL_SIZE = 48
WALL_SIZE = 3
RED_EDGE_GAP = 5
RED_OFFSET = WALL_SIZE + RED_EDGE_GAP
RED_SIZE = CELL_SIZE - WALL_SIZE - 2 * RED_EDGE_GAP
FINAL_RED_REFRESHES = 2
RED_TRAIL_LENGTH = 4
RESTART_DELAY_MS = 5000

COLS = (display_width - 2 * PADDING) // CELL_SIZE
ROWS = (display_height - 2 * PADDING) // CELL_SIZE
MAZE_WIDTH = COLS * CELL_SIZE
MAZE_HEIGHT = ROWS * CELL_SIZE
MAZE_X = (display_width - MAZE_WIDTH) // 2
MAZE_Y = (display_height - MAZE_HEIGHT) // 2

NORTH = 1
EAST = 2
SOUTH = 4
WEST = 8

_BITS = (NORTH, EAST, SOUTH, WEST)
_OPPOSITE = (SOUTH, WEST, NORTH, EAST)
_DX = (0, 1, 0, -1)
_DY = (-1, 0, 1, 0)


class MazeApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        self.name = "Maze Solver"
        self.sleep_ms = 50
        self.launched = False
        self._passages = []
        self._entry = 0
        self._exit = 0
        self._solution = []
        self._solution_index = 0
        self._red_cells = []
        self._waiting_for_initial = False
        self._final_refreshes = 0
        self._solved = False
        self._restart_at = None

    @staticmethod
    def _index(col, row):
        return row * COLS + col

    @staticmethod
    def _position(index):
        return index % COLS, index // COLS

    def _neighbors(self, index, only_unvisited=None):
        col, row = self._position(index)
        result = []
        for direction in range(4):
            next_col = col + _DX[direction]
            next_row = row + _DY[direction]
            if not (0 <= next_col < COLS and 0 <= next_row < ROWS):
                continue
            neighbor = self._index(next_col, next_row)
            if only_unvisited is not None and only_unvisited[neighbor]:
                continue
            result.append((direction, neighbor))
        return result

    def _generate(self):
        """Generate a perfect maze, starting at a random left-edge cell."""
        count = COLS * ROWS
        self._passages = [0] * count
        visited = bytearray(count)
        entry_row = random.randint(0, ROWS - 1)
        self._entry = self._index(0, entry_row)
        visited[self._entry] = 1
        stack = [self._entry]

        while stack:
            current = stack[-1]
            choices = self._neighbors(current, visited)
            if not choices:
                stack.pop()
                continue
            direction, neighbor = choices[random.randint(0, len(choices) - 1)]
            self._passages[current] |= _BITS[direction]
            self._passages[neighbor] |= _OPPOSITE[direction]
            visited[neighbor] = 1
            stack.append(neighbor)

        self._exit = self._farthest_right_cell()
        self._passages[self._entry] |= WEST
        self._passages[self._exit] |= EAST

    def _farthest_right_cell(self):
        """Choose the most distant right-edge cell as the exit."""
        count = COLS * ROWS
        distance = [-1] * count
        distance[self._entry] = 0
        queue = [self._entry]
        head = 0
        while head < len(queue):
            current = queue[head]
            head += 1
            col, row = self._position(current)
            for direction in range(4):
                if not (self._passages[current] & _BITS[direction]):
                    continue
                next_col = col + _DX[direction]
                next_row = row + _DY[direction]
                if not (0 <= next_col < COLS and 0 <= next_row < ROWS):
                    continue
                neighbor = self._index(next_col, next_row)
                if distance[neighbor] >= 0:
                    continue
                distance[neighbor] = distance[current] + 1
                queue.append(neighbor)

        best = self._index(COLS - 1, 0)
        for row in range(1, ROWS):
            candidate = self._index(COLS - 1, row)
            if distance[candidate] > distance[best]:
                best = candidate
        return best

    @staticmethod
    def _black_hline(x, y, length):
        for offset in range(WALL_SIZE):
            display.black.hline(x, y + offset, length + 1, 1)

    @staticmethod
    def _black_vline(x, y, length):
        for offset in range(WALL_SIZE):
            display.black.vline(x + offset, y, length + 1, 1)

    def _draw_maze(self):
        display.clear()
        for row in range(ROWS):
            for col in range(COLS):
                cell = self._index(col, row)
                passages = self._passages[cell]
                x = MAZE_X + col * CELL_SIZE
                y = MAZE_Y + row * CELL_SIZE
                if not (passages & NORTH):
                    self._black_hline(x, y, CELL_SIZE)
                if not (passages & WEST):
                    self._black_vline(x, y, CELL_SIZE)
                if row == ROWS - 1 and not (passages & SOUTH):
                    self._black_hline(x, y + CELL_SIZE, CELL_SIZE)
                if col == COLS - 1 and not (passages & EAST):
                    self._black_vline(x + CELL_SIZE, y, CELL_SIZE)

    def _prepare_solver(self):
        """Find the solution once so animation never paints a wrong turn."""
        count = COLS * ROWS
        parent = [-1] * count
        parent[self._entry] = self._entry
        queue = [self._entry]
        head = 0

        while head < len(queue):
            current = queue[head]
            head += 1
            if current == self._exit:
                break
            col, row = self._position(current)
            for direction in range(4):
                if not (self._passages[current] & _BITS[direction]):
                    continue
                next_col = col + _DX[direction]
                next_row = row + _DY[direction]
                if not (0 <= next_col < COLS and 0 <= next_row < ROWS):
                    continue
                neighbor = self._index(next_col, next_row)
                if parent[neighbor] >= 0:
                    continue
                parent[neighbor] = current
                queue.append(neighbor)

        path = []
        current = self._exit
        while current != self._entry:
            path.append(current)
            current = parent[current]
        path.append(self._entry)
        path.reverse()
        self._solution = path
        self._solution_index = 0

    def _solver_step(self):
        if self._solution_index >= len(self._solution):
            return None
        cell = self._solution[self._solution_index]
        self._solution_index += 1
        return cell

    def _set_cell_red(self, cell, enabled):
        col, row = self._position(cell)
        x = MAZE_X + col * CELL_SIZE + RED_OFFSET
        y = MAZE_Y + row * CELL_SIZE + RED_OFFSET
        display.red.fill_rect(x, y, RED_SIZE, RED_SIZE, 1 if enabled else 0)
        display.black.fill_rect(x, y, RED_SIZE, RED_SIZE, 0)

    def _advance_red_trail(self, cell):
        if len(self._red_cells) >= RED_TRAIL_LENGTH:
            previous = self._red_cells.pop(0)
            self._set_cell_red(previous, False)
        self._set_cell_red(cell, True)
        self._red_cells.append(cell)

    def _start(self):
        print("Generating maze")
        self._generate()
        self._draw_maze()
        self._prepare_solver()
        self._red_cells = []
        self._waiting_for_initial = True
        self._final_refreshes = 0
        self._solved = False
        self._restart_at = None
        display.update(led_feedback=False)

    def run(self):
        if self.launched:
            self._start()
            return
        if self._solved:
            if not display.is_done_updating():
                return
            if self._restart_at is None:
                self._restart_at = time.ticks_add(
                    time.ticks_ms(), RESTART_DELAY_MS)
                return
            if time.ticks_diff(time.ticks_ms(), self._restart_at) >= 0:
                self._start()
            return
        if not display.is_done_updating():
            return
        if self._waiting_for_initial:
            self._waiting_for_initial = False

        if self._final_refreshes:
            # Repaint every red cell so even the last solver cells receive
            # enough red pulls to reach full saturation rather than gray.
            display.update(
                red_only=True, preserve_red=True, led_feedback=False)
            self._final_refreshes -= 1
            if not self._final_refreshes:
                self._solved = True
                print("Maze solved")
            return

        cell = self._solver_step()
        if cell is None:
            self._solved = True
            return
        self._advance_red_trail(cell)
        # Repaint only the four-cell trail. Each cell receives enough repeated
        # pulls to develop red, then falls out of the drive window but stays red.
        display.update(red_only=True, preserve_red=True, led_feedback=False)
        if cell == self._exit:
            self._final_refreshes = FINAL_RED_REFRESHES
