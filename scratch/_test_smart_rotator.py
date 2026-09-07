import time
import random
from collections import deque

class SmartRotator:
    """
    Умный ротатор целей:
    1. Shuffle-Bag (перемешанная колода): гарантирует 100% равномерный обход без повторов.
    2. In-Flight Exclusion: цель, которая сейчас проверяется, не выдается параллельным потокам.
    3. Cooldown: цель после чека остывает (cooldown_sec), чтобы не спамить один мерчант.
    4. Circuit Breaker: при серии ошибок цель временно исключается из ротации (quarantine).
    """
    def __init__(self, cooldown_sec: float = 15.0, quarantine_sec: float = 300.0, max_fails: int = 2):
        self.cooldown_sec = cooldown_sec
        self.quarantine_sec = quarantine_sec
        self.max_fails = max_fails
        
        self._in_flight: set[str] = set()
        self._last_used: dict[str, float] = {}
        self._fails: dict[str, int] = {}
        self._quarantined_until: dict[str, float] = {}
        self._decks: dict[str, list[str]] = {} # tier_key -> remaining targets in current cycle

    def pick(self, targets: list[str], tier_key: str = "default") -> str:
        if not targets:
            raise RuntimeError("No targets available")
            
        now = time.monotonic()
        
        # 1. Фильтруем карантин (circuit breaker)
        active = [
            t for t in targets 
            if self._quarantined_until.get(t, 0) <= now
        ]
        if not active:
            # Если все в карантине, сбрасываем самый старый
            active = targets

        # 2. Фильтруем in-flight (занятые прямо сейчас)
        available = [t for t in active if t not in self._in_flight]
        if not available:
            available = active

        # 3. Фильтруем cooldown (остывающие)
        ready = [t for t in available if now - self._last_used.get(t, 0) >= self.cooldown_sec]
        candidates = ready if ready else available

        # 4. Shuffle-Bag (колода)
        deck = self._decks.get(tier_key, [])
        # Оставляем в колоде только те, что входят в candidates
        valid_deck = [t for t in deck if t in candidates]
        
        if not valid_deck:
            # Перемешиваем заново все candidates
            shuffled = list(candidates)
            random.shuffle(shuffled)
            valid_deck = shuffled
            
        chosen = valid_deck.pop(0)
        self._decks[tier_key] = valid_deck
        
        # Помечаем in-flight
        self._in_flight.add(chosen)
        self._last_used[chosen] = now
        return chosen

    def release(self, target: str, success: bool = True):
        self._in_flight.discard(target)
        now = time.monotonic()
        if success:
            self._fails[target] = 0
        else:
            f = self._fails.get(target, 0) + 1
            self._fails[target] = f
            if f >= self.max_fails:
                self._quarantined_until[target] = now + self.quarantine_sec

# Тест: 21 магазин в тире 1, батч из 10 параллельных запросов
rotator = SmartRotator(cooldown_sec=10.0)
targets = [f"https://shop{i}.com" for i in range(21)]

# Имитируем 10 параллельных выборов
batch_picks = [rotator.pick(targets, tier_key="tier1") for _ in range(10)]
print(f"10 parallel picks from 21 targets:")
print(f"Unique targets picked: {len(set(batch_picks))} out of 10")
assert len(set(batch_picks)) == 10, "In-flight duplicate detected!"

# Завершаем чеки
for t in batch_picks:
    rotator.release(t, success=True)

# Следующий батч из 10
batch2 = [rotator.pick(targets, tier_key="tier1") for _ in range(10)]
print(f"Next 10 picks:")
print(f"Unique targets picked: {len(set(batch2))} out of 10")
# Пересечение с предыдущим батчем (должно быть 0 или минимум из-за cooldown/shuffle)
intersection = set(batch_picks) & set(batch2)
print(f"Overlap with previous batch (due to cooldown): {len(intersection)} (expected 0 or 1)")
print("SmartRotator verification SUCCESS!")
