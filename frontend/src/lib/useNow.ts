import { useEffect, useState } from 'react'

const TICK_MS = 100
// Шаг обновления секундомера. Меньше, чем точность показа (десятые доли секунды):
// при обновлении раз в секунду цифра росла бы рывками. 100 мс — компромисс:
// счётчик движется плавно, но компонент не перерисовывается десятки раз в секунду.

/**
 * Текущее время, обновляемое, пока ``active``.
 *
 * Нужен для тикающих секундомеров: без него прошедшее время считается только в
 * момент перерисовки, а во время выполнения этапа события не приходят — цифра
 * замирала бы до следующего события SSE.
 *
 * Когда ``active`` ложно, таймер не создаётся: на завершённом прогоне лишние
 * перерисовки не нужны.
 */
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!active) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(timer)
  }, [active])

  return now
}